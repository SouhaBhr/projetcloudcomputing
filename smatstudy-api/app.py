import os
import json
import re
import random

from typing import Optional, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient

from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

app = FastAPI()


class QuestionRequest(BaseModel):
    question: str = ""
    filename: Optional[str] = None
    mode: Literal["normal", "persona"] = "normal"

# Retrieves a retriever configured for the MongoDB collection and VertexAI embeddings.
def get_retriever(filename: Optional[str] = None):
    client = MongoClient(os.environ.get("MONGO_URI"))
    collection = client["smartstudy"]["context"]

    embeddings = VertexAIEmbeddings(
        model_name="text-embedding-005",
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "europe-west1"),
    )

    vector_store = MongoDBAtlasVectorSearch(
        collection=collection,
        embedding=embeddings,
        index_name="vector_index",
    )

    search_kwargs = {"k": 5}
    if filename:
        search_kwargs["pre_filter"] = {"source": {"$eq": filename}}

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )


def get_llm():
    """LLM standard pour le chat."""
    return ChatVertexAI(
        model_name="gemini-2.5-flash",
        temperature=0,
        max_output_tokens=2048,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "europe-west1"),
    )


def get_llm_quiz():
    """LLM dédié au quiz : plus de tokens + mode JSON garanti."""
    return ChatVertexAI(
        model_name="gemini-2.5-flash",
        temperature=0.7,
        max_output_tokens=4096,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("LOCATION", "europe-west1"),
        response_mime_type="application/json",
    )


@app.get("/")
def health_check():
    return {"status": "SmartStudy API is running"}


@app.post("/ask")
def ask(request: QuestionRequest):
    try:
        retriever = get_retriever(request.filename)
        llm = get_llm()

        persona_prompt = """
You are SmartStudy, a formal academic tutor.

Your role is to help students study course material professionally and pedagogically.

Rules:
- Answer ONLY using the provided context.
- If the answer is not in the context, say clearly that you do not know.
- Always cite the source/page whenever possible.
- Provide concise but educational explanations.
- Summarize complex ideas clearly.
- Add a Study Tip ("Tip:") — a memory aid, mnemonic, key concept to remember, or a way to connect this idea to something else.
- At the end of each answer, ask one short pedagogical follow-up question to help the student reflect, NOT just a recap question. Make them think.
- Respond in the same language as the question.

Context:
{context}
"""

        normal_prompt = """
You are an assistant that answers questions using only the provided context.
If the answer is not in the context, say that you do not know.
Be clear and concise. Respond in the same language as the question.

Context:
{context}
"""

        system_prompt = persona_prompt if request.mode == "persona" else normal_prompt

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
            ]
        )

        qa_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, qa_chain)

        response = rag_chain.invoke({"input": request.question})

        return {
            "mode": request.mode,
            "question": request.question,
            "filename": request.filename,
            "answer": response["answer"],
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {str(e)}",
        )


@app.post("/quiz")
def quiz(request: QuestionRequest):
    try:
        retriever = get_retriever(request.filename)
        llm = get_llm_quiz()  # ← LLM dédié au quiz

        topic = request.question or "the uploaded material"

        docs = retriever.invoke(topic)

        random.shuffle(docs)
        selected_docs = docs[:5]

        context = "\n\n".join([doc.page_content for doc in selected_docs])

        quiz_prompt = f"""
You are SmartStudy, a formal academic tutor creating an INTERACTIVE quiz.

Create exactly 5 multiple-choice questions based ONLY on the context below.

Respond with VALID JSON ONLY using this EXACT schema:

{{
  "questions": [
    {{
      "question": "the question text",
      "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
      "correct_index": 0,
      "explanation": "Why this answer is correct, with a short pedagogical insight",
      "source": "page or section reference, or empty string"
    }}
  ]
}}

Rules:
- Exactly 5 questions.
- Each question has exactly 4 options.
- correct_index is 0, 1, 2, or 3 (0 = first option).
- Mix difficulty: 2 easy (recall), 2 medium (understanding), 1 harder (application).
- Do NOT use external knowledge — only the context.
- Write the quiz in the same language as the topic when possible, otherwise English.
- Keep options and explanations CONCISE (max 2 sentences each) to ensure the response fits.
- The "explanation" field should help the student LEARN, not just confirm the answer.

Context:
{context}

Topic:
{topic}
"""

        response = llm.invoke(quiz_prompt)
        raw = response.content.strip()

        # clean up code blocks if the model wrapped the JSON in ```json ... ``` or ``` ... ```
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        try:
            quiz_data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {
                "mode": "quiz",
                "topic": topic,
                "filename": request.filename,
                "error": f"Le modèle n'a pas renvoyé un JSON valide: {e}",
                "raw": raw,
            }

        return {
            "mode": "quiz",
            "topic": topic,
            "filename": request.filename,
            "quiz": quiz_data,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {str(e)}",
        )