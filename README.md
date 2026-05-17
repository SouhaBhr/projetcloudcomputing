# SmartStudy – Cloud-Based AI Academic Assistant

# Notes

This repository represents the academic project structure and implementation.

Cloud deployment and infrastructure configuration were performed directly through Google Cloud services during development.

## Overview

SmartStudy is a cloud-based academic assistant designed to help students interact intelligently with course material uploaded as PDF documents(see DEMO - VIDEO.mp4).

The system uses a Retrieval-Augmented Generation (RAG) architecture combining:

* Google Cloud Storage
* Google Cloud Functions
* Google Cloud Run
* MongoDB Atlas Vector Search
* Vertex AI Embeddings
* Gemini 2.5 Flash
* Streamlit frontend

Users can:

* upload PDF course material,
* ask questions about the uploaded documents,
* receive context-aware academic explanations,
* generate quizzes automatically from the study material.

---

# Project Architecture

```text
User
  ↓
Frontend (Streamlit Web UI)
  ↓
Cloud Run API (/ask and /quiz)
  ↓
MongoDB Atlas Vector Search
  ↓
Gemini 2.5 Flash (Vertex AI)

---------------------------------------

PDF Upload
  ↓
Google Cloud Storage
  ↓
Cloud Function Trigger
  ↓
PDF Chunking + Embeddings
  ↓
MongoDB Atlas
```

---

# Repository Structure

```text
projetcloudcomputing/
│
├── api/
│   ├── app.py
│   └── requirements.txt
│
├── ingestion/
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── interface.py
│   ├── requirements.txt
│   ├── package.json
│   └── package-lock.json
│
└── .gitignore
```

---

# Components

## 1. API (`api/`)

The API is deployed on Google Cloud Run.

It exposes:

* `/ask` → ask questions about uploaded documents
* `/quiz` → automatically generate quizzes from the uploaded material

Main technologies:

* FastAPI
* LangChain
* Gemini 2.5 Flash
* MongoDB Atlas Vector Search

The API retrieves relevant chunks from MongoDB and uses Gemini to generate educational responses.

---

## 2. Ingestion Pipeline (`ingestion/`)

The ingestion pipeline is deployed as a Google Cloud Function.

Workflow:

1. User uploads a PDF to Google Cloud Storage
2. Cloud Function is automatically triggered
3. PDF text is extracted and chunked
4. Embeddings are generated using Vertex AI
5. Chunks and embeddings are stored in MongoDB Atlas

Main technologies:

* PyPDFLoader
* RecursiveCharacterTextSplitter
* Vertex AI Embeddings
* MongoDB Atlas

---

## 3. Frontend (`frontend/`)

The frontend provides the user interface.

Features:

* upload PDF documents
* ask questions
* generate quizzes
* interact with the assistant through a chat interface

Main technology:

* Streamlit

---

# Environment Variables

The project uses several environment variables:

```text
MONGO_URI
GOOGLE_CLOUD_PROJECT
LOCATION
```

Sensitive credentials should normally be stored using environment variables or secret managers.
For simplicity during the academic project, some values may appear directly in the code.

---

# Features

## Ask Mode

Users can ask questions about uploaded course material.

The assistant:

* retrieves relevant chunks,
* answers using only the provided context,
* provides pedagogical explanations.

---

## Quiz Mode

Users can generate quizzes automatically from uploaded documents.

The quiz system:

* generates questions from retrieved context,
* mixes question types,
* encourages active learning.

---
