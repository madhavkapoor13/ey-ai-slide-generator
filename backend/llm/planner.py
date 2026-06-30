import json

from backend.llm.client import client
from backend.llm.prompts import OPERATING_MODEL_PROMPT, PROCESS_FLOW_PROMPT


def create_slide_spec(title: str, content: str):
    return _create_spec(title, content, PROCESS_FLOW_PROMPT)


def create_operating_model_spec(title: str, content: str):
    return _create_spec(title, content, OPERATING_MODEL_PROMPT)


def _create_spec(title: str, content: str, system_prompt: str):

    response = client.chat.completions.create(
        model="gpt-4o-mini",

        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"""
Slide Title:
{title}

Slide Content:
{content}
"""
            }
        ],

        response_format={
            "type": "json_object"
        },

        temperature=0
    )

    return json.loads(
        response.choices[0].message.content
    )
