from flask import Flask
from flask_jwt_extended import JWTManager
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    jwt = JWTManager(app)

    from app.routes import main
    app.register_blueprint(main)

    return app
