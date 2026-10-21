import json
import os

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

from llm_app.utils.common_class import CommonLlmApi, LLMConfig
from llm_app.utils.common_function import TokenSlidingChatMemory

_ = load_dotenv(find_dotenv())
api_Key = os.getenv('BIGMODEL_API_KEY', '')
base_url_http = os.getenv('BIGMODEL_ZAI_URL', '')
base_url = os.getenv('BIGMODEL_BASE_URL', '')
model_name = os.getenv('BIGMODEL_MODEL_NAME', '')

llm_config = LLMConfig(api_key=api_Key, base_url=base_url_http, model_name=model_name)
llm_chat = CommonLlmApi(llmconfig=llm_config, temperature=0.7, top_p=0.9, stream=True)  # type: ignore
msg_sliding = TokenSlidingChatMemory(
    max_total_tokens=5000, system_prompt='你是一个数学家,善于解决各种数学问题'
)
msg_sliding.clear_history()
if __name__ == '__main__':
    while True:
        user_input = input('用户 : ')
        if user_input.lower() == 'q':
            break
        try:
            msg_sliding.add_message(role='user', content=user_input)
            results = llm_chat.chat(msg_sliding.get_messages())
            full_content = ''
            print('AI : ', end='')
            for line in results.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # 去掉 'data: ' 前缀
                        if data_str == '[DONE]':
                            break
                        data = json.loads(data_str)
                        delta = data['choices'][0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            full_content += content
                            print(content, end='', flush=True)  # [新增] 实时打印
            print()
            print(
                f'系统提示: 当前context已使用{msg_sliding.current_total_tokens}/{msg_sliding.max_total_tokens},使用率:'
            )  # [新增] 换行
            msg_sliding.add_message(role='assistant', content=full_content)
        except Exception as e:
            print(f'程序错误:{e}')
