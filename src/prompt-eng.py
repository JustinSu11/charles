##################################################
# Library Imports
##################################################

import os
import argparse

from dotenv import load_dotenv
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI


##################################################
# Start of Code
##################################################

# Load .env file
load_dotenv()

# Access Secrets
# TODO - add conditional switching for different api keys using argparse library
API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise ValueError("API_KEY not found in environment variables")

##################################################
# Model Setup
# ---
# OpenRouter makes use of the langchain_openai library
##################################################

# TODO - Add conditional switching for model selection. Use argparse library

# ! - Issues running this model, possibly due to rate limiting
# model = ChatOpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=API_KEY,
#     model="qwen/qwen3-next-80b-a3b-instruct:free"
# )

# model = ChatOpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=API_KEY,
#     model=""
# )

# NOTE - Using deepseek for testing because it is cheaper for prototyping
model = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
    model="deepseek/deepseek-v3.2"
)

##################################################
# Prompt / Context Engineering Section
##################################################



# Example usage
response = model.invoke("What is the meaning of life? Wrong answers only.")
print(response.content)