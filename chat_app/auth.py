from quart_auth import AuthUser
from models import User


class _User(AuthUser):
    def __init__(self, auth_id):
        super().__init__(auth_id)
        self.data = None

    async def load_user(self):
        self.data = await User.get_or_none(id=self.auth_id)
