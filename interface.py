import streamlit as st
from google.cloud import storage
import time
import requests

st.set_page_config(page_title="SmartStudy Tutor", page_icon="🎓", layout="centered")

# --- CONFIGURATION ---
BUCKET_NAME = "pdf_bucket_project"
PROJECT_ID = "projet-cloud-computing-493007"

API_BASE_URL = "https://smartstudy-api-64317660927.europe-west1.run.app"
API_ASK_URL = f"{API_BASE_URL}/ask"

st.title("SmartStudy Tutor")
st.markdown("### Bienvenue dans ton espace d'apprentissage intelligent")
st.write("Télécharge ton cours en PDF pour commencer la session.")

# État
if "file_ready" not in st.session_state:
    st.session_state.file_ready = False
if "messages" not in st.session_state:
    st.session_state.messages = []


# --- SECTION 1 : UPLOAD ---
with st.container():
    uploaded_file = st.file_uploader("Choisis ton fichier PDF", type="pdf")

    if uploaded_file is not None and not st.session_state.file_ready:
        if st.button("Lancer l'analyse du cours"):
            with st.status("Traitement du document...", expanded=True) as status:
                st.write(" Envoi du fichier vers Google Cloud Storage...")
                client = storage.Client(project=PROJECT_ID)
                bucket = client.bucket(BUCKET_NAME)
                blob = bucket.blob(uploaded_file.name)
                blob.upload_from_file(uploaded_file)
                st.write("Fichier envoyé.")

                st.write(" Analyse et indexation du document en cours...")
                st.write("(Cela peut prendre 30 à 60 secondes)")
                time.sleep(45)

                st.write("Document indexé !")
                status.update(label="Analyse terminée !", state="complete", expanded=False)

            st.session_state.file_ready = True
            st.balloons()

# --- SECTION 2 : CHAT ---


# Bouton pour changer de PDF
if st.session_state.file_ready:
    if st.button("📄 Charger un autre PDF"):
        st.session_state.file_ready = False
        st.session_state.messages = []
        st.session_state.current_filename = None
        st.rerun()



if st.session_state.file_ready:
    st.success(f"**Document actif :** `{st.session_state.current_filename}`")
    st.divider()
    st.subheader(" Pose tes questions sur le cours")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: Peux-tu me résumer les points clés ?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Je cherche dans tes documents..."):
                try:
                    res = requests.post(
                        API_ASK_URL,  # ← Note le /ask à la fin
                        json={"question": prompt, "filename": st.session_state.current_filename },
                        timeout=120,
                    )

                    if res.status_code == 200:
                        data = res.json()
                        reponse_ia = data.get("answer", "Pas de réponse reçue.")
                        st.markdown(reponse_ia)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": reponse_ia}
                        )
                    else:
                        error_msg = f"Erreur {res.status_code} : {res.text}"
                        st.error(error_msg)

                except Exception as e:
                    st.error(f"Erreur de connexion : {e}")


