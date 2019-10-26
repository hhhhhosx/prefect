import box
import cloudpickle
import pytest
from unittest.mock import MagicMock

import prefect
from prefect.engine.result_handlers import SecretResultHandler
from prefect.tasks.secrets import Secret
from prefect.utilities.configuration import set_temporary_config
from prefect.utilities.exceptions import AuthorizationError, ClientError


def test_secret_requires_name_at_init():
    with pytest.raises(
        TypeError, match="missing 1 required positional argument: 'name'"
    ):
        secret = Secret()


def test_create_secret():
    secret = Secret(name="test")
    assert secret.name == "test"
    assert secret.max_retries == 2
    assert secret.retry_delay.total_seconds() == 1.0
    assert isinstance(secret.result_handler, SecretResultHandler)


def test_create_secret_with_different_retry_settings():
    secret = Secret(name="test", max_retries=0, retry_delay=None)
    assert secret.name == "test"
    assert secret.max_retries == 0
    assert secret.retry_delay is None


def test_create_secret_with_result_handler():
    secret = Secret(name="test", result_handler=lambda x: None)
    assert isinstance(secret.result_handler, SecretResultHandler)


def test_secret_raises_if_doesnt_exist():
    secret = Secret(name="test")
    with set_temporary_config({"cloud.use_local_secrets": True}):
        with pytest.raises(ValueError, match="not found"):
            secret.run()


def test_secret_value_pulled_from_context():
    secret = Secret(name="test")
    with set_temporary_config({"cloud.use_local_secrets": True}):
        with prefect.context(secrets=dict(test=42)):
            assert secret.run() == 42
        with pytest.raises(ValueError):
            secret.run()


def test_secret_value_depends_on_use_local_secrets(monkeypatch):
    response = {"errors": "Malformed Authorization header"}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    secret = Secret(name="test")
    with set_temporary_config(
        {"cloud.use_local_secrets": False, "cloud.auth_token": None}
    ):
        with prefect.context(secrets=dict()):
            with pytest.raises(ClientError):
                secret.run()


def test_secrets_use_client(monkeypatch):
    response = {"data": {"secretValue": '"1234"'}}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)
    with set_temporary_config(
        {"cloud.auth_token": "secret_token", "cloud.use_local_secrets": False}
    ):
        my_secret = Secret(name="the-key")
        val = my_secret.run()
    assert val == "1234"


def test_cloud_secrets_use_context_first(monkeypatch):
    response = {"data": {"secretValue": '"1234"'}}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)
    with set_temporary_config(
        {"cloud.auth_token": "secret_token", "cloud.use_local_secrets": False}
    ):
        with prefect.context(secrets={"the-key": "foo"}):
            my_secret = Secret(name="the-key")
            val = my_secret.run()
    assert val == "foo"


def test_cloud_secrets_use_context_first_but_fallback_to_client(monkeypatch):
    response = {"data": {"secretValue": '"1234"'}}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)
    with set_temporary_config(
        {"cloud.auth_token": "secret_token", "cloud.use_local_secrets": False}
    ):
        with prefect.context(secrets={}):
            my_secret = Secret(name="the-key")
            val = my_secret.run()
    assert val == "1234"


def test_cloud_secrets_remain_plain_dictionaries(monkeypatch):
    response = {"data": {"secretValue": {"a": "1234", "b": [1, 2, {"c": 3}]}}}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)
    with set_temporary_config(
        {"cloud.auth_token": "secret_token", "cloud.use_local_secrets": False}
    ):
        my_secret = Secret(name="the-key")
        val = my_secret.run()
    assert val == {"a": "1234", "b": [1, 2, {"c": 3}]}
    assert isinstance(val, dict) and not isinstance(val, box.Box)
    val2 = val["b"]
    assert isinstance(val2, list) and not isinstance(val2, box.BoxList)
    val3 = val["b"][2]
    assert isinstance(val3, dict) and not isinstance(val3, box.Box)


def test_cloud_secrets_auto_load_json_strings(monkeypatch):
    response = {"data": {"secretValue": '{"x": 42}'}}
    post = MagicMock(return_value=MagicMock(json=MagicMock(return_value=response)))
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)
    with set_temporary_config(
        {"cloud.auth_token": "secret_token", "cloud.use_local_secrets": False}
    ):
        my_secret = Secret(name="the-key")
        val = my_secret.run()

    assert isinstance(val, dict)


def test_local_secrets_auto_load_json_strings():
    secret = Secret(name="test")
    with set_temporary_config({"cloud.use_local_secrets": True}):
        with prefect.context(secrets=dict(test='{"x": 42}')):
            assert secret.run() == {"x": 42}
        with pytest.raises(ValueError):
            secret.run()


def test_local_secrets_remain_plain_dictionaries():
    secret = Secret(name="test")
    with set_temporary_config({"cloud.use_local_secrets": True}):
        with prefect.context(secrets=dict(test={"x": 42})):
            assert isinstance(prefect.context.secrets["test"], dict)
            val = secret.run()
            assert val == {"x": 42}
            assert isinstance(val, dict) and not isinstance(val, box.Box)


def test_secret_is_pickleable():
    secret = Secret(name="long name")
    new = cloudpickle.loads(cloudpickle.dumps(secret))
    assert new.name == "long name"
    assert new.max_retries == 2
    assert new.retry_delay.total_seconds() == 1.0
    assert isinstance(new.result_handler, SecretResultHandler)
