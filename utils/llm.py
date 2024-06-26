import os
import re
import json
import logging
import random

import validators

import anthropic

import openai

from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

from urlextract import URLExtract
from bs4 import BeautifulSoup
from langdetect import detect


class UnsupportedModelException(Exception):
    """Exception raised for unsupported models."""
    def __init__(self, model, message="Model not supported"):
        self.model = model
        self.message = message
        super().__init__(self.message)


class UnsupportedValidationException(Exception):
    """Exception raised for unsupported validation."""
    def __init__(self, validation, message="Validation type not supported"):
        self.validation = validation
        self.message = message
        super().__init__(self.message)


def text_to_chunks(text, chunk_size=175000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]


def find_urls(text):
    extractor = URLExtract()
    potential_urls = extractor.find_urls(text, check_dns=True)
    valid_urls = []
    for url in potential_urls:
        if url.endswith('.'):
            url = url[:-1]
        if validators.url(url):
            valid_urls.append(url)
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


def validate_article_html(html, language_code, min_article_score, model):
    max_size = 10000
    if len(html) > max_size:
        return False

    soup = BeautifulSoup(html, 'html.parser')

    if soup.find('script'):
        return False

    allowed_tags = ['div', 'p', 'ul', 'ol', 'li']
    allowed_attributes = ['class', 'id', 'alt', 'data-front-page-score']

    # Sanitize HTML tags and attributes
    for tag in soup.find_all():
        if tag.name not in allowed_tags:
            tag.decompose()
        for attr in list(tag.attrs.keys()):
            if attr not in allowed_attributes:
                del tag[attr]

    article_div = soup.find('div', class_='article',\
            attrs=lambda attrs: 'data-front-page-score'\
            in attrs and min_article_score <= int(attrs['data-front-page-score']) <= 5)
    if not article_div:
        return False

    article_title_div = article_div.find('div', class_='article-title')
    if not article_title_div:
        return False

    article_content = article_div.find('div', class_='article-content hidden')
    if not article_content:
        return False

    content_text = article_content.text.strip()
    llm_output_language = detect(content_text)
    logging.info(f"detected output language {llm_output_language}")
    if language_code not in llm_output_language:
        logging.info(f"Wrong Language from LLM. \
                Expected {language_code}\
                got {llm_output_language} from {model}")
        return False

    return True


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
                        "text": f"{instructions}\n\n{text_chunk}"
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
                "content": f"{instructions}\n\n{text_chunk}"
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
            content=f"{instructions}\n\n{text_chunk}"
            )
        ]
    )

    return chat_completion.choices[0].message.content


def fetch_llm_response(text, instructions, model, validation=None, language_filter=None, min_article_score=None):

    if model == "Claude 3h":
        chunks = text_to_chunks(text,chunk_size=(190000-len(instructions)))
        response = send_to_anthropic(chunks[0], instructions,'claude-3-haiku-20240307')
    elif model == "GPT-3.5t":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_openai(chunks[0],instructions,'gpt-3.5-turbo')
    elif model == "Open Mixtral":
        chunks = text_to_chunks(text,chunk_size=(31000-len(instructions)))
        response = send_to_mistral(chunks[0], instructions,'open-mixtral-8x7b')
    elif model == "Random":
        models = ["Claude 3h", "GPT-3.5t", "Open Mixtral"]
        model = random.choice(models)
        return fetch_llm_response(text, instructions, model, validation, language_filter, min_article_score)
    else:
        raise UnsupportedModelException(model)
        
    if validation is None:
        return response, model
    elif validation == "url":
        logging.info(response)
        return find_urls(response), model
    elif validation == "html":
        return find_html(response), model
    elif validation == "html-article":
        html = find_html(response)
        if validate_article_html(html, language_filter, min_article_score, model):
            return html, model
        else:
            logging.info("bad formatting from LLM")
            return None, model
    elif validation == "json":
        return find_json(response), model
    else:
        raise UnsupportedValidationException(validation)
