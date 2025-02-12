import time
import os
import gc
import json
import pickle
import secrets
import pandas as pd
from langchain.schema import Document
from dotenv import load_dotenv
from functions import get_chain,get_answer
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import CSVLoader,TextLoader,PyPDFLoader,UnstructuredExcelLoader
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_huggingface import HuggingFaceEndpoint
from langchain_community.vectorstores import FAISS
from flask import Flask,request, render_template, redirect, url_for, flash, jsonify
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from langchain.memory import ConversationBufferMemory,ConversationSummaryBufferMemory



app = Flask(__name__)
app.secret_key = secrets.token_hex(24)  # Required for flash messages
os.environ['CURL_CA_BUNDLE'] = ''
# Upload folder configuration
UPLOAD_FOLDER = 'Document/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['store_answer_feedback'] = 'Store_Ans'

answer_file_path = os.path.join(app.config['store_answer_feedback'], 'answers.json')
feedback_file_path = os.path.join(app.config['store_answer_feedback'], 'feedback.json')

if not os.path.exists(answer_file_path):
    with open(answer_file_path, 'w') as f:
        json.dump([], f)  # Initialize with an empty list

def get_files_in_folder(folder_path):
    # Allowed file extensions
    allowed_extensions = ('.csv', '.pdf', '.xlsx', '.txt')
    
    # Get all files with the allowed extensions
    files = [os.path.join(folder_path, filename) for filename in os.listdir(folder_path) if filename.endswith(allowed_extensions)]
    del[allowed_extensions]
    gc.collect()
    return files

@app.route('/')
def index():
    """Render the homepage with a list of allowed files."""
    # Allowed file extensions
    allowed_extensions = ('.csv', '.pdf', '.xlsx', '.txt')
    # Get the list of files with allowed extensions
    files = [os.path.basename(f) for f in get_files_in_folder(app.config['UPLOAD_FOLDER']) if f.endswith(allowed_extensions)]
    del[allowed_extensions]
    gc.collect()
    return render_template('index.html', files=files)

@app.route('/uploads', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    allowed_extensions = ('.csv', '.pdf', '.xlsx', '.txt')
    
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))
    
    if file and file.filename.lower().endswith(allowed_extensions):
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File uploaded successfully')
    else:
        flash(f'Invalid file type. Only {", ".join(allowed_extensions)} files are allowed.')
    del[allowed_extensions,file]
    gc.collect()
    return redirect(url_for('index'))

@app.route('/delete/<filename>')
def delete_file(filename):
    """Delete a file.
    Args:
    filename(['String']) : Path of file to be deleted.
    """
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.remove(file_path)
    flash('File deleted successfully.')
    pkl_file_name = filename.split('.')[0]+'.pkl'
    if os.path.exists(os.path.join(pkl_file_name)):                
        os.remove(os.path.join(pkl_file_name))
    del [file_path,pkl_file_name]
    gc.collect()
    return redirect(url_for('index'))

# general prompt for model
prompt_temp = '''You are a Guide AI. Your role is to provide guidance strictly on related topics available in given context only and provide answers in a proper and interactive way. 
--> Make sure given things while answering:
    - If the information is not explicitly stated in the context, respond with: "Information is not available for this question." Avoid using external knowledge or inferred answers.
    - Answer will include only direct context-based answers, and if it is not clearly in the context respond with, "Information is not available for this question.

--> Before providing an answer, go through all the rules and try to find which rule will be best for the related question. and Provide consise and brief answer in response.
    If you are confusing to answer the question then Response "Information not available please provide more information." and if asked question is confusing and question is not explicitly stated then  
    Response "Information not available for this question." and do not make any guess to give an answer for question.Be appropreate do not answer out of context.

**Strictly Follow Rules:**
1. **One Word in Question:**
   If a question contains only one word, find the number of questions that contain the specific word(s). Then, combine all the questions containing the specific word(s) and provide the answer based on the combined context.
   - **Process:**
        1. Find how many questions contain the word(s) and provide a list of all those questions. Combine their context to generate a synthesized answer.
        2. Separate each question with a new line in the provided response.
        3. If no question contains the word(s), respond with: "Specific word-related information not available."

2. **Two Words in Question:**
   If a question contains only two words and if a relevant question is found containing those words, provide the answer for that question. If no such question exists, find the number of questions that contain the specific word(s) and provide the answer based on the combined context.
   - **Process:**
        1. Search for the exact word(s) in the list of questions.
        2. If a relevant question is found, return the associated answer.
        3. If no exact match is found, count how many questions contain the word(s) and provide a list of all those questions. Combine their context to generate a synthesized answer.
        4. Separate each question with a new line in the provided response.
        5. If no question contains the word(s), respond with: "Specific word-related information not available."

3. **Three Words in Question:**
   If a question contains only three words and if a relevant question is found containing those words, provide the answer for that question. If no such question exists, find the number of questions that contain the specific word(s) and provide the answer based on the combined context.
   - **Process:**
        1. Search for the exact word(s) in the list of questions.
        2. If a relevant question is found, return the associated answer.
        3. If no exact match is found, count how many questions contain the word(s) and provide a list of all those questions. Combine their context to generate a synthesized answer.
        4. Separate each question with a new line in the provided response.
        5. If no question contains the word(s), respond with: "Specific word-related information not available."
    
4. Please check if the following question uses the exact or similar concepts. If the concepts match and you can confidently answer based on that, then provide an answer. If the concepts do not align or you are unsure, respond with: "Answer is not found in provided context. 
    Provide more information." If the key term aligns with the intended meaning, answer the question. If the key term does not match the intended meaning, say "Answer is not found, Provide more information."

5. **Exact Match with Variations:**
    Search in the vector database using only the Question field. Ensure your response fully matches the question in meaning, 
    even if slight variations are present (e.g., adding phrases before or after the question like "related to," "regarding," etc.). 
    Double or triple-check if the core question aligns with the context. If not, respond with: "Answer for this question is not available."

6. **Irrelevant or Misleading Variations:**
    Search in the vector database using only the Question field. If the user's question includes additional phrases or variations (before or after the main question)
    that are irrelevant to the provided context, respond with: "Please ask questions from provided information."

7. **Unrelated or Confusing Questions:** 
   If the question is unrelated to the context, unclear, or contains confusing parts, respond with: "Please provide more information related to the question."

8. **Word Confusion:**
   If a question has words that don't match the context, double-check the terms. If the context doesn’t cover the exact term, respond with: "Provide more information about the question."

9. **Greetings and Common Phrases:**
   - If a question contains greetings (e.g., "Hello, Hi"), respond with: "Hello, please ask your question."
   - If a user thanks you, reply with: "You're welcome! Feel free to ask if you have any other questions."
   - For small talk (e.g., "How are you?"), reply with: "Please ask document related questions."

10. **User Ask for fullform of Word, double check for word full form available in context.**
    Do not provide full form for sort word, if fullform of word available in context ex. question contains like what stand for DL , ML ? or what is fullform of MI ? etc. if 
    fullform of word is available in context then only answer else Response "Information not available in given context." 
    If you are confusing to answer the question then Response "Information not available."

11. 

**Example Non-Contextual Questions (if available in context then give answer else Respond with "I don't know"):**
- "How do I use ChatGPT?, how do i use SAP", how do i use black-Box? etc.

**Example Questions and Responses:**
- **What can you do?** → "I provide guidance on topics based on the provided context."
- **Are you a robot?** → "I am an AI designed to assist with inquiries."
- **Where do you get your information?** → "I use specific data to generate answers."
- **Can you give me an example?** → "Sure! You can ask about topics like 'What is my release code?'"
- **Information about context** or **tell me about context** → "'Give information about context you know.'"

Context:
{context} \n
Question:
{question} \n
'''
prompt =  PromptTemplate(template=prompt_temp,input_variables=['context', 'question'])
chat_history = []
memory = ConversationBufferMemory()
# memory = ConversationSummaryBufferMemory(llm=ChatGroq(model='llama-3.1-70b-versatile',api_key='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',temperature=0,max_retries=2),
#                                          memory_key="chat_history",
#                                          verbose=True)

# embeding is representation of data into vector formate 
embedings = HuggingFaceBgeEmbeddings()
# define model and asign key # if do sample is true then it uses random sample technique and 
# llm = HuggingFaceEndpoint(repo_id='meta-llama/Llama-3.1-8B-Instruct', temperature=0.001, huggingfacehub_api_token='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', max_new_tokens=512,do_sample=False)

@app.route('/ask', methods=['POST'])
def get_ans_from_csv():
    ''' this function is used to get answer from given csv.

    Args:
    doc_file([CSV]): comma separated file 
    query_text :  Question

    Returns: Answer
    '''
    
    query_text = request.form.get('query_text')
    doc_file = request.form.get('selected_file')
    print('doc_file::',doc_file)
    selected_language = request.form.get('selected_language')
    query_text = query_text.lower() 
    # ext = doc_file.split('.')[1]
    

    if query_text :
        start_time = time.time()
        if not doc_file or doc_file == "Select a document":
            flash("Please select a document to proceed.")
            return redirect(url_for('index'))
        else:
            if doc_file.endswith('txt'):
                loader = TextLoader(os.path.join('Document', doc_file), encoding='utf-8')
                data = loader.load()
            elif doc_file.endswith('csv'):
                loader = CSVLoader(os.path.join('Document',doc_file))
                prompt =  PromptTemplate(template=prompt_temp,input_variables=['context','question'])
                data = loader.load()
            elif doc_file.endswith('pdf'):
                loader = PyPDFLoader(os.path.join('Document',doc_file))
                data = []
                for page in loader.lazy_load():
                    data.append(page)
            elif doc_file.endswith(('xlsx','xls')):
                loader = UnstructuredExcelLoader(os.path.join('Document',doc_file))
                prompt =  PromptTemplate(template=prompt_temp,input_variables=['context','question'])
                data = loader.load()
                print('data::',data)
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=700,chunk_overlap=100)
            docs = text_splitter.split_documents(data)
            
            # to load pickle file 
            pickle_file_name = doc_file.split('.')[0]+'.pkl'
            if os.path.isfile(os.path.join(pickle_file_name)):
                with open(os.path.join(pickle_file_name),mode='rb') as f:
                    vector_index = pickle.load(f)
            else:
                # if pickle file not available
                vector_index = FAISS.from_documents(docs, embedding=embedings)
            # model
            llm = ChatGroq(model='llama-3.1-70b-versatile',api_key='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',temperature=0,max_retries=2)

            # function is used to get answer
            chain = get_chain(llm,prompt,vector_index)
            # res_dict = get_answer(chain,query_text,embedings)
            
            res_dict = get_answer(chain,query_text)
            
            # print('res_dict:',res_dict)
            # # if pickle file not available
            # doc = [Document(page_content=res_dict['en'])]
            
            # print('doc:::',doc)
            # ans_index = FAISS.from_documents(doc, embedding=embedings)
            # query_text_1 = '''Keep only required information in Answer do not add extra knowledge and if many Question and Answer available then saperate them by new line etc.
            # do not show any prompt related information in answer. Context:{context} \n Question: {question}'''
            # prompt_1 =  PromptTemplate(template=prompt_temp,input_variables=['context', 'question'])
            # chain = get_chain(llm,prompt_1,ans_index)
            # res_dict = get_answer(chain,query_text_1)
            
            
            if not os.path.isfile(os.path.join(pickle_file_name)):
                with open(os.path.join(pickle_file_name),mode='wb') as f:
                        pickle.dump(vector_index,f)

            # Prepare the answer dictionary
            que_ans_dict = {'doc': doc_file, query_text:res_dict}
            res_ans =que_ans_dict[query_text][selected_language]
            
            del [pickle_file_name,vector_index,chain,llm,
                res_dict,que_ans_dict,loader,data,prompt]
            gc.collect()

        end_time = time.time()
        print('time_taken :',end_time-start_time)
        return jsonify({'answer': res_ans})
    else:
        return redirect(url_for('index'))
    



@app.route('/save_answers', methods=['POST'])
def save_answers():
    """Save answer data to answers.json."""
    data = request.json
    print('answer_file_path:',answer_file_path)
    with open(answer_file_path, 'r+') as f:
        answers = json.load(f)
        answers.append(data)  # Append new data
        f.seek(0)  # Move to the beginning of the file
        json.dump(answers, f, indent=4)  # Save updated data
    del[data]
    gc.collect()
    return jsonify({'message': 'Answer data saved successfully'}), 200

@app.route('/save_feedback', methods=['POST'])
def save_feedback():
    """Save user feedback."""
    feedback_data = request.json
    # Initialize feedback file if it doesn't exist
    if not os.path.exists(feedback_file_path):
        with open(feedback_file_path, 'w') as f:
            json.dump([], f)  # Start with an empty list
    
    print('feedback_file_path::',feedback_file_path)
    with open(feedback_file_path, 'r+') as f:
        feedbacks = json.load(f)
        feedbacks.append(feedback_data)  # Append new feedback
        f.seek(0)  # Move to the beginning of the file
        json.dump(feedbacks, f, indent=4)  # Save updated feedback

    return jsonify({'message': 'Feedback saved successfully'}), 200


if __name__=='__main__':
    app.run(debug=True)


