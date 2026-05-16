import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account
import time
import requests
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from pymongo import MongoClient
from datetime import datetime

st.set_page_config(page_title="SmartStudy Tutor", page_icon="🎓", layout="centered")

# --- CONFIGURATION ---
BUCKET_NAME = "pdf_bucket_project"
PROJECT_ID = "projet-cloud-computing-493007"
MONGO_URI = "mongodb+srv://projetcloud:projetcloud@geminirag.shbfocl.mongodb.net/?appName=GeminiRAG"
MONGO_DB = "smartstudy"
MONGO_COLLECTION = "chat_history"

API_BASE_URL = "https://smartstudy-api-64317660927.europe-west1.run.app"
API_ASK_URL = f"{API_BASE_URL}/ask"
API_QUIZ_URL = f"{API_BASE_URL}/quiz"


# --- HELPERS ---
def get_storage_client():
    try:
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            return storage.Client(project=PROJECT_ID, credentials=creds)
    except Exception:
        pass
    return storage.Client(project=PROJECT_ID)


def get_chat_history(session_id: str) -> MongoDBChatMessageHistory:
    return MongoDBChatMessageHistory(
        session_id=session_id,
        connection_string=MONGO_URI,
        collection_name=MONGO_COLLECTION,
        database_name=MONGO_DB,
    )


@st.cache_data(ttl=30)
def load_past_sessions():
    """Fetch all past sessions from MongoDB, sorted by most recent."""
    try:
        client = MongoClient(MONGO_URI)
        col = client[MONGO_DB][MONGO_COLLECTION]
        sessions = col.aggregate([
            {"$group": {
                "_id": "$SessionId",
                "last_updated": {"$max": "$_id"},
                "message_count": {"$sum": 1},
            }},
            {"$sort": {"last_updated": -1}},
            {"$limit": 30},
        ])
        return list(sessions)
    except Exception:
        return []


@st.cache_data(ttl=60)
def load_session_messages(session_id: str):
    """Load messages from a past session and return as list of dicts."""
    try:
        client = MongoClient(MONGO_URI)
        col = client[MONGO_DB][MONGO_COLLECTION]
        # Each document in the collection is one message
        docs = list(col.find({"SessionId": session_id}).sort("_id", 1))
        messages = []
        for doc in docs:
            # langchain_mongodb stores messages inside a "History" field as JSON
            history_data = doc.get("History", {})
            msg_type = history_data.get("type", "")
            content = history_data.get("data", {}).get("content", "")
            if msg_type == "human":
                messages.append({"role": "user", "content": content})
            elif msg_type == "ai":
                messages.append({"role": "assistant", "content": content})
        return messages
    except Exception:
        return []


def format_session_label(session_id: str):
    """Turn 'cours.pdf_1716800000' into (filename, date)."""
    parts = session_id.rsplit("_", 1)
    if len(parts) == 2:
        filename = parts[0]
        try:
            ts = int(parts[1])
            date = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
            return filename, date
        except ValueError:
            pass
    return session_id, ""


# --- STATE INITIALIZATION ---
defaults = {
    "file_ready": False,
    "messages": [],
    "current_filename": None,
    "session_id": None,
    "quiz_data": None,
    "quiz_answers": {},
    "quiz_submitted": False,
    "show_quiz": False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# --- SIDEBAR ---
with st.sidebar:
    st.title("🎓 SmartStudy")

    mode = st.radio(
        "Mode du tuteur",
        options=["persona", "normal"],
        format_func=lambda x: "🎓 Tuteur Personna" if x == "persona" else "📝 Mode Normal",
    )

    st.divider()

    if st.button("✏️ Nouvelle conversation", use_container_width=True):
        st.session_state.file_ready = False
        st.session_state.messages = []
        st.session_state.current_filename = None
        st.session_state.session_id = None
        st.session_state.quiz_data = None
        st.session_state.quiz_answers = {}
        st.session_state.quiz_submitted = False
        st.session_state.show_quiz = False
        st.rerun()

    if st.session_state.file_ready and not st.session_state.show_quiz:
        if st.button("🧠 Lancer un quiz", use_container_width=True, type="primary"):
            st.session_state.show_quiz = True
            st.session_state.quiz_data = None
            st.session_state.quiz_answers = {}
            st.session_state.quiz_submitted = False
            st.rerun()

    st.divider()
    st.markdown("#### 🕐 Conversations récentes")

    past_sessions = load_past_sessions()

    if not past_sessions:
        st.caption("Aucune conversation sauvegardée.")
    else:
        for s in past_sessions:
            sid = s["_id"]
            filename, date = format_session_label(sid)
            is_active = sid == st.session_state.session_id
            prefix = "▶ " if is_active else ""
            label = f"{prefix}📄 {filename}\n🕐 {date}" if date else f"{prefix}📄 {filename}"

            if st.button(label, key=f"sess_{sid}", use_container_width=True):
                msgs = load_session_messages(sid)
                parts = sid.rsplit("_", 1)
                st.session_state.messages = msgs
                st.session_state.session_id = sid
                st.session_state.current_filename = parts[0] if len(parts) == 2 else sid
                st.session_state.file_ready = True
                st.session_state.show_quiz = False
                st.rerun()


# --- MAIN ---
st.title("🎓 SmartStudy Tutor")
st.markdown("### Bienvenue dans ton espace d'apprentissage intelligent")


# --- SECTION 1 : UPLOAD ---
if not st.session_state.file_ready:
    st.write("Télécharge ton cours en PDF pour commencer la session.")

    with st.container():
        uploaded_file = st.file_uploader("Choisis ton fichier PDF", type="pdf")

        if uploaded_file is not None:
            if st.button("Lancer l'analyse du cours"):
                with st.status("Traitement du document...", expanded=True) as status:
                    st.write("📤 Envoi du fichier vers Google Cloud Storage...")
                    client = get_storage_client()
                    bucket = client.bucket(BUCKET_NAME)
                    blob = bucket.blob(uploaded_file.name)
                    blob.upload_from_file(uploaded_file)
                    st.session_state.current_filename = uploaded_file.name
                    st.write(f"✅ Fichier `{uploaded_file.name}` envoyé.")

                    st.write("🔍 Analyse et indexation du document en cours...")
                    st.write("(Cela peut prendre 30 à 60 secondes)")
                    time.sleep(45)

                    st.write("✅ Document indexé !")
                    status.update(label="Analyse terminée !", state="complete", expanded=False)

                st.session_state.session_id = f"{uploaded_file.name}_{int(time.time())}"
                st.session_state.file_ready = True
                st.session_state.messages = []
                # Invalide le cache pour que la nouvelle session apparaisse
                load_past_sessions.clear()
                st.balloons()
                st.rerun()


# --- SECTION 2A : QUIZ ---
if st.session_state.file_ready and st.session_state.show_quiz:
    st.divider()

    col_title, col_close = st.columns([5, 1])
    with col_title:
        st.subheader("🧠 Quiz interactif")
    with col_close:
        if st.button("✖ Fermer", use_container_width=True):
            st.session_state.show_quiz = False
            st.session_state.quiz_data = None
            st.session_state.quiz_answers = {}
            st.session_state.quiz_submitted = False
            st.rerun()

    if st.session_state.quiz_data is None:
        with st.spinner("🎓 Le mentor prépare ton quiz..."):
            try:
                res = requests.post(
                    API_QUIZ_URL,
                    json={"question": "", "filename": st.session_state.current_filename},
                    timeout=120,
                )
                if res.status_code == 200:
                    data = res.json()
                    quiz_obj = data.get("quiz")
                    if isinstance(quiz_obj, dict) and "questions" in quiz_obj:
                        st.session_state.quiz_data = quiz_obj["questions"]
                        st.rerun()
                    else:
                        st.error("Le quiz n'a pas pu être généré correctement.")
                        st.json(data)
                else:
                    st.error(f"Erreur {res.status_code} : {res.text}")
            except Exception as e:
                st.error(f"Erreur de connexion : {e}")

    if st.session_state.quiz_data:
        questions = st.session_state.quiz_data

        if not st.session_state.quiz_submitted:
            st.info(f"📋 **{len(questions)} questions** — Choisis une réponse pour chacune, puis soumets.")

            for i, q in enumerate(questions):
                with st.container(border=True):
                    st.markdown(f"**Question {i+1}.** {q['question']}")
                    choice = st.radio(
                        "Ta réponse :",
                        options=list(range(len(q["options"]))),
                        format_func=lambda x, opts=q["options"]: f"{chr(65+x)}. {opts[x]}",
                        key=f"quiz_q_{i}",
                        index=None,
                    )
                    if choice is not None:
                        st.session_state.quiz_answers[i] = choice

            all_answered = len(st.session_state.quiz_answers) == len(questions)
            if st.button("Soumettre mes réponses", disabled=not all_answered,
                         use_container_width=True, type="primary"):
                st.session_state.quiz_submitted = True
                st.rerun()

            if not all_answered:
                st.caption(f"Réponses données : {len(st.session_state.quiz_answers)}/{len(questions)}")

        else:
            score = sum(
                1 for i, q in enumerate(questions)
                if st.session_state.quiz_answers.get(i) == q["correct_index"]
            )
            total = len(questions)
            pct = round(100 * score / total)

            if pct >= 80:
                st.success(f"🏆 Excellent ! Score : **{score}/{total}** ({pct}%)")
                feedback = "Tu maîtrises bien ce chapitre. Continue comme ça !"
            elif pct >= 50:
                st.warning(f"👍 Pas mal ! Score : **{score}/{total}** ({pct}%)")
                feedback = "Quelques notions à revoir. Regarde bien les explications ci-dessous."
            else:
                st.error(f"📚 À retravailler. Score : **{score}/{total}** ({pct}%)")
                feedback = "Pas de panique, c'est en se trompant qu'on apprend ! Lis bien les corrections."

            st.markdown(f"_{feedback}_")
            st.progress(pct / 100)
            st.divider()

            for i, q in enumerate(questions):
                user_answer = st.session_state.quiz_answers.get(i)
                correct = q["correct_index"]
                is_correct = user_answer == correct

                with st.container(border=True):
                    icon = "✅" if is_correct else "❌"
                    st.markdown(f"### {icon} Question {i+1}")
                    st.markdown(f"**{q['question']}**")

                    for j, opt in enumerate(q["options"]):
                        prefix = chr(65 + j)
                        if j == correct:
                            st.markdown(f"- **{prefix}. {opt}**  _(bonne réponse)_")
                        elif j == user_answer and not is_correct:
                            st.markdown(f"- {prefix}. {opt}  _(ta réponse)_")
                        else:
                            st.markdown(f"- {prefix}. {opt}")

                    st.info(f"💡 **Explication :** {q['explanation']}")
                    if q.get("source"):
                        st.caption(f"Source : {q['source']}")

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Refaire un nouveau quiz", use_container_width=True):
                    st.session_state.quiz_data = None
                    st.session_state.quiz_answers = {}
                    st.session_state.quiz_submitted = False
                    st.rerun()
            with col2:
                if st.button("💬 Retour au chat", use_container_width=True):
                    st.session_state.show_quiz = False
                    st.rerun()


# --- SECTION 2B : CHAT ---
elif st.session_state.file_ready:
    st.success(f"**Document actif :** `{st.session_state.current_filename}`")
    st.divider()

    mode_label = "🎓 Mentor" if mode == "persona" else "📝 Direct"
    st.subheader(f"Pose tes questions — Mode {mode_label}")
    st.caption("Astuce : utilise le bouton **🧠 Lancer un quiz** dans la sidebar pour te tester.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: Résume les points clés pour moi"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        body = {
            "question": prompt,
            "filename": st.session_state.current_filename,
            "mode": mode,
        }

        with st.chat_message("assistant"):
            with st.spinner("Je réfléchis..."):
                try:
                    res = requests.post(API_ASK_URL, json=body, timeout=120)

                    if res.status_code == 200:
                        data = res.json()
                        reponse_ia = data.get("answer", "Aucune réponse reçue.")
                        st.markdown(reponse_ia)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": reponse_ia}
                        )

                        # Sauvegarde dans MongoDB
                        if st.session_state.session_id:
                            history = get_chat_history(st.session_state.session_id)
                            history.add_user_message(prompt)
                            history.add_ai_message(reponse_ia)
                            # Invalide le cache pour que la sidebar se mette à jour
                            load_past_sessions.clear()
                            load_session_messages.clear()

                    else:
                        st.error(f"Erreur {res.status_code} : {res.text}")

                except Exception as e:
                    st.error(f"Erreur de connexion : {e}")
