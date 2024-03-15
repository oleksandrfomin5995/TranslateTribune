import re
import json

import validators

import anthropic

import openai

from urlextract import URLExtract

from bs4 import BeautifulSoup


class UnsupportedModelException(Exception):
    def __init__(self, model, message="Model not supported"):
        self.model = model
        print(model)
        self.message = message
        super().__init__(self.message)


def text_to_chunks(text, chunk_approx_tokens, avg_token_length):

    chunk_approx_chars = chunk_approx_tokens * avg_token_length
    chunks = []
    text_length = len(text)
    start_index = 0

    while start_index < text_length:
        end_index = min(start_index + chunk_approx_chars, text_length)
        chunk = text[start_index:end_index]
        chunks.append(chunk)
        start_index = end_index

    return chunks


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
    
def send_to_anthropic(text_chunk, instructions):
    client = anthropic.Anthropic()

    message = client.messages.create(
        model="claude-3-opus-20240229",
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


def send_to_openai(text_chunk, instructions):
    client = openai.OpenAI()

    chat_completion = client.chat.completions.create(
    model="gpt-4-turbo-preview",
    messages=[
            {
                "role": "user",
                "content": f"{instructions} {text_chunk}"
            }
        ]
    )

    return chat_completion.choices[0].message.content

def fetch_llm_response(text, instructions, model, chunk_approx_tokens, avg_token_length, validation=None):

    if model == "Claude 3":
        chunks = text_to_chunks(text,chunk_approx_tokens,avg_token_length)
        response = send_to_anthropic(chunks[0], instructions)
    elif model == "GPT-4":
        chunks = text_to_chunks(text,chunk_approx_tokens,avg_token_length)
        response = send_to_openai(chunks[0], instructions)
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
