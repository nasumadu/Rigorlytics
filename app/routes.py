from flask import Blueprint, request, jsonify, render_template

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("index.html")

@main.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question", "")

    if not question:
        return jsonify({"error": "No question provided"}), 400

    response = {
        "question": question,
        "answer": f"Rigorlytics received your question: {question}. RAG pipeline coming soon.",
        "status": "success"
    }

    return jsonify(response), 200

@main.route("/health")
def health():
    return jsonify({"status": "Rigorlytics is running", "version": "1.0"}), 200
