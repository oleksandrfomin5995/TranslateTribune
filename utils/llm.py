import os
import re
import json

import validators

import anthropic

import openai

from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

from urlextract import URLExtract

from bs4 import BeautifulSoup


class UnsupportedModelException(Exception):
    def __init__(self, model, message="Model not supported"):
        self.model = model
        print(model)
        self.message = message
        super().__init__(self.message)

def text_to_chunks(text, chunk_size=175000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]


def find_urls(text):
    extractor = URLExtract()
    potential_urls = extractor.find_urls(text, check_dns=True)
    valid_urls = [url for url in potential_urls if validators.url(url)]
    return valid_urls


def find_html(text):
    soup = BeautifulSoup(text, 'html.parser')

    largest_block = None
    largest_size = 0

    for element in soup.children:
        if element.name and len(list(element.descendants)) > largest_size:
            largest_block = element
            largest_size = len(list(element.descendants))

    if largest_block:
        return largest_block.prettify()
    else:
        return ""

def find_json(text):
    json_match = re.search(r'({.*})', text, re.DOTALL)

    if json_match:
        json_str = json_match.group(1)
        try:
            return json.loads(json_str)
        except Exception:
            return []
    else:
        return [] 
    
def send_to_anthropic(text_chunk, instructions, model_id="claude-3-opus-20240229"):
    client = anthropic.Anthropic()

    message = client.messages.create(
        model=model_id,
        max_tokens=4000,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{instructions} {text_chunk}"
                    }
                ]
            }
        ]
    )
    
    return message.content[0].text


def send_to_openai(text_chunk, instructions, model_id="gpt-4-turbo-preview"):
    client = openai.OpenAI()

    chat_completion = client.chat.completions.create(
    model=model_id,
    messages=[
            {
                "role": "user",
                "content": f"{instructions} {text_chunk}"
            }
        ]
    )

    return chat_completion.choices[0].message.content


def send_to_mistral(text_chunk, instructions, model_id="mistral-large-latest"):
    client = MistralClient(
            api_key=os.environ["MISTRAL_API_KEY"]
            )

    chat_completion = client.chat(
    model=model_id,
    messages=[ChatMessage(
            role="user",
            content=f"{instructions} {text_chunk}"
            )
        ]
    )

    return chat_completion.choices[0].message.content


def fetch_llm_response(text, instructions, model, validation=None):

    if model == "Claude 3":
        chunks = text_to_chunks(text,chunk_size=(190000-len(instructions)))
        response = send_to_anthropic(chunks[0], instructions)
    elif model == "Claude 2.1":
        chunks = text_to_chunks(text,chunk_size=(190000-len(instructions)))
        response = send_to_anthropic(chunks[0], instructions,'claude-2.1')
    elif model == "GPT-4":
        chunks = text_to_chunks(text,chunk_size=(190000-len(instructions)))
        response = send_to_openai(chunks[0],instructions)
    elif model == "GPT-3.5t":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_openai(chunks[0],instructions,'gpt-3.5-turbo')
    elif model == "Mistral-LG":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_mistral(chunks[0], instructions)
    elif model == "Mistral-MD":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_mistral(chunks[0], instructions,'mistral-medium-latest')
    elif model == "Mistral-SM":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_mistral(chunks[0], instructions,'mistral-small-latest')
    elif model == "Open Mixtral":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_mistral(chunks[0], instructions,'open-mixtral-8x7b')
    else:
        raise UnsupportedModelException(model)

    if validation is None:
        return response
    elif validation == "url":
        return find_urls(response)
    elif validation == "html":
        return find_html(response)
    elif validation == "json":
        return find_json(response)
    else:
        return None

