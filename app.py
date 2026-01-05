# Flask 入口

from flask import Flask, jsonify
from db import get_connection

app = Flask(__name__)

# demo:查看配送中心
@app.route("/", methods=["GET"])
def get_centers():
    conn = get_connection()
    cursor = conn.cursor(as_dict=True)

    cursor.execute("""
        SELECT *
        FROM centers
    """)

    centers = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(centers)

if __name__ == "__main__":
    app.run(debug=True)

