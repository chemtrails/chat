from tortoise.models import Model
from tortoise import fields


class User(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=200, unique=True)
    password = fields.CharField(max_length=200)


class Message(Model):
    id = fields.IntField(pk=True)
    date = fields.DatetimeField(auto_now_add=True)
    text = fields.TextField()
    author = fields.ForeignKeyField("models.User", related_name="sent")
    recipient = fields.ForeignKeyField("models.User", related_name="received")
