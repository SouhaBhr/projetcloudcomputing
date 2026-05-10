import streamlit as st
from google.cloud import storage
import time
import requests
from langchain_mongodb.chat_message_histories import MongoChatMessageHistory

st.set_page_config(page_title="SmartStudy Tutor", page_icon="🎓", layout="centered")

# --- CONFIGURATION ---
BUCKET_NAME = "pdf_bucket_project"
PROJECT_ID = "projet-cloud-computing-493007"

API_BASE_URL = "https://smartstudy-api-64317660927.europe-west1.run.app"
API_ASK_URL = f"{API_BASE_URL}/ask"

st.title("SmartStudy Tutor")
st.markdown("### Welcome to your intelligent learning space")
st.write("Upload your course as PDF to start the session.")

# State initialization
if "file_ready" not in st.session_state:
    st.session_state.file_ready = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_filename" not in st.session_state:
    st.session_state.current_filename = None
if "save_to_history" not in st.session_state:
    st.session_state.save_to_history = False

# Initialize MongoDB Chat History
chat_with_history = None


# --- SECTION 1: FILE UPLOAD ---
with st.container():
    uploaded_file = st.file_uploader("Choose your PDF file", type="pdf")

    if uploaded_file is not None and not st.session_state.file_ready:
        if st.button("Start Course Analysis"):
            with st.status("Processing document...", expanded=True) as status:
                st.write(" Sending file to Google Cloud Storage...")
                client = storage.Client(project=PROJECT_ID)
                bucket = client.bucket(BUCKET_NAME)
                blob = bucket.blob(uploaded_file.name)
                blob.upload_from_file(uploaded_file)
                st.write("File uploaded.")

                st.write(" Document analysis and indexing in progress...")
                st.write("(This may take 30 to 60 seconds)")
                time.sleep(45)

                st.write("Document indexed!")
                status.update(label="Analysis complete!", state="complete", expanded=False)

            st.session_state.file_ready = True
            st.balloons()

# --- SECTION 2: CHAT ---


# Button to change PDF
if st.session_state.file_ready:
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📄 Load Another PDF"):
            st.session_state.file_ready = False
            st.session_state.messages = []
            st.session_state.current_filename = None
            st.session_state.save_to_history = False
            st.rerun()
    
    with col2:
        if st.button("💾 " + ("Disable History" if st.session_state.save_to_history else "Enable History")):
            st.session_state.save_to_history = not st.session_state.save_to_history
            st.rerun()



if st.session_state.file_ready:
    st.success(f"**Active Document:** `{st.session_state.current_filename}`")
    
    # Display history status
    if st.session_state.save_to_history:
        st.info("💾 History enabled - your conversations will be saved")
    
    st.divider()
    st.subheader(" Ask Questions About Your Course")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: Summarize the key points for me"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching through your documents..."):
                try:
                    res = requests.post(
                        API_ASK_URL,  # ← Note the /ask at the end
                        json={"question": prompt, "filename": st.session_state.current_filename },
                        timeout=120,
                    )

                    if res.status_code == 200:
                        data = res.json()
                        reponse_ia = data.get("answer", "No response received.")
                        st.markdown(reponse_ia)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": reponse_ia}
                        )
                        
                        # Save to MongoDB only if enabled
                        if st.session_state.save_to_history:
                            if chat_with_history is None and st.session_state.current_filename:
                                chat_with_history = MongoChatMessageHistory(
                                    session_id=st.session_state.current_filename,
                                    connection_string="mongodb+srv://projetcloud:projetcloud@geminirag.shbfocl.mongodb.net/?appName=GeminiRAG",
                                    collection_name="chat_history",
                                    database_name="smartstudy"
                                )
                            if chat_with_history:
                                chat_with_history.add_user_message(prompt)
                                chat_with_history.add_ai_message(reponse_ia)
                    else:
                        error_msg = f"Error {res.status_code}: {res.text}"
                        st.error(error_msg)

                except Exception as e:
                    st.error(f"Connection error: {e}")

