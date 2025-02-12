import textwrap
import gc
from langchain.chains.retrieval_qa.base import RetrievalQA
from deep_translator import GoogleTranslator
from langchain_community.vectorstores import FAISS
from langchain_core.messages import HumanMessage

# Define text wrapping function
def wrap_text_preserve_new_line(text, width=110):
    lines = text.split('\n')
    wrapped_lines = [textwrap.fill(line, width=width) for line in lines]
    wrapped_text = '\n'.join(wrapped_lines)

    del[lines,wrapped_lines]
    gc.collect()
    return wrapped_text 

def get_chain(llm,prompt,vector_index):

    chain = RetrievalQA.from_chain_type(llm,
                                    input_key='question',
                                    retriever=vector_index.as_retriever(),
                                    return_source_documents=True,
                                    chain_type_kwargs={'prompt':prompt,
                                                       }
                                    )
    del [llm,prompt,vector_index]
    gc.collect()
    return chain

def get_answer(chain,query_text):
    ''' this function is used to retrive answer of given query_text

    Args:
    llm : Pretrained Model
    PROMPT : If query_text related question is not available in csv file then it return dont know
    vector_index : Used for faster search of sementic query_text from data
    query_text : Question

    Returns : Answer
    '''
    # RetrivalQA used for retriving answer form asked question 
    answer_dict = chain.invoke({'question':query_text})
    # chat_history.extend([HumanMessage(content=query_text), answer_dict['result']])
    print('answer_dict',answer_dict)

    res_dict = {'en':answer_dict['result']}
    print('res_dict:',res_dict)
    
    answer = answer_dict['result']
    print('answer::',answer)
    
    # To translate
    tgt_lang_lst = ['gu','hi','ta']
    for tgt_lang in tgt_lang_lst:
        translated = GoogleTranslator(source='en', target = tgt_lang).translate(answer)

        res =wrap_text_preserve_new_line(translated)
        res_dict[tgt_lang] = res
    del [chain,answer_dict,tgt_lang_lst]
    gc.collect()
    return res_dict


