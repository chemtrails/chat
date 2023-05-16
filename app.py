import json
import asyncio

from quart import websocket, Quart, render_template, request, redirect, jsonify
from quart_auth import AuthUser, AuthManager, current_user, login_required, login_user, logout_user, Unauthorized

from tortoise import Tortoise
from tortoise.expressions import Q

from xxhash import xxh32_hexdigest

from broker import Broker
from models import Message, User
from auth import _User


START_BATCH = 10
BATCH = 2

app = Quart(__name__)
app.secret_key = "12344321"
auth_manager = AuthManager()
auth_manager.user_class = _User
broker = Broker()
auth_manager.init_app(app)


# PREPARE


@app.before_serving
async def first():
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',
        modules={"models": ["models"]}
    )
    await Tortoise.generate_schemas()


@app.before_websocket
@app.before_request
async def load():
    await current_user.load_user()


# INDEX


@app.route("/")
async def index():
    err = request.args.get("error")
    users = await User.exclude(id=current_user.auth_id).limit(10)
    return await render_template("index.html", err=err, users=users, user=current_user)


# AUTH


@app.post("/register")
async def register():
    form = await request.form
    name = form.get("username")
    password = form.get("password")
    try:
        user = await User.create(name=name, password=xxh32_hexdigest(password))
        login_user(AuthUser(user.id))
        return redirect("/")
    except Exception as e:
        print(e)
        return redirect(f"/?error=User already exists")


@app.post("/login")
async def login():
    form = await request.form
    name = form.get("username")
    password = form.get("password")
    user = await User.get_or_none(name=name, password=xxh32_hexdigest(password))
    if user is not None:
        login_user(AuthUser(user.id))
        return redirect("/")
    return redirect("/?error=Wrong credentials")


@app.route("/logout")
async def logout():
    logout_user()
    return redirect("/")


# CHAT


@app.route("/chat/<name>")
@login_required
async def chat(name):
    user = current_user.data
    to = await User.filter(name=name).first()
    messages = await Message.filter(
        (Q(recipient=user) & Q(author=to)) | (Q(recipient=to) & Q(author=user))
    ).order_by("-date").limit(START_BATCH)

    # TODO: use flex-direction: column-reverse instead of reversing list
    messages = list(messages)
    messages.reverse()
    return await render_template("chat.html", messages=messages, user=current_user, to=name)


# FETCH


@app.get("/messages")
async def get_messages():
    last_id = int(request.args.get("id"))
    name = request.args.get("name")

    # GET MESSAGES < ID

    user = current_user.data
    to = await User.filter(name=name).first()
    messages = await Message.filter(
        Q(id__lt=last_id), Q(
            (Q(recipient=user) & Q(author=to)) | (Q(recipient=to) & Q(author=user))
        )
    ).order_by("-date").limit(BATCH)
    if messages:
        cursor = messages[-1].id
    else:
        messages = []
        cursor = 0
    template = await render_template("batch.html", messages=messages, user=current_user)
    return jsonify({"html": template, "cursor": cursor})


# ERROR


@app.errorhandler(Unauthorized)
async def redirect_to_login(*_: Exception):
    return redirect("/?error=You are not logged in")


@app.errorhandler(404)
async def err_four(e):
    return redirect("/?error=Page not found")


@app.errorhandler(500)
async def err_five(e):
    return redirect("/?error=Something went wrong")


# SOCKET


async def _receive(c):
    while True:
        if c is not None:
            message = await websocket.receive()
            loaded = json.loads(message)
            author = await User.get_or_none(id=c.auth_id)
            rec = await User.get_or_none(name=loaded.get("to"))
            msg = await Message.create(
                text=loaded.get("msg"),
                author=author,
                recipient=rec
            )
            await broker.publish(msg)


@app.websocket("/ws")
@login_required
async def ws():
    try:
        task = asyncio.ensure_future(_receive(current_user))
        async for message in broker.subscribe():
            if message.recipient.name == current_user.data.name:
                await websocket.send(str(message.text))
    finally:
        task.cancel()
        await task


if __name__ == "__main__":
    app.run(debug=True)
