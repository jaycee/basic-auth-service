from contextlib import closing
import argparse
import unittest
from unittest import mock
import io

import asynctest

import fixtures

import yaml

from ..manage_credentials import (
    parse_args,
    call_model_method,
    db_call,
    print_result,
    main,
)
from ...testing import create_test_config
from ...db.testing import (
    TEST_DB_DSN,
    ensure_database,
)
from ...db.model import APICredentials


class ParseArgsTest(fixtures.TestWithFixtures):

    def test_parse_args(self):
        """Command line arguments are parsed."""
        tempdir = self.useFixture(fixtures.TempDir())
        file_path = tempdir.join('config.yaml')
        create_test_config(filename=file_path)
        args = parse_args(args=['--config', file_path, 'list'])
        with closing(args.config):
            config = yaml.load(args.config.read())
        self.assertEqual(
            {'db': {'dsn': 'postgresql:///basic-auth-test'}},
            config)


class CallModelMethodTest(asynctest.TestCase):

    def setUp(self):
        super().setUp()
        ensure_database()

    async def test_call_model_method(self):
        """call_model_method executes Model calls in a transaction."""
        await call_model_method(
            self.loop, TEST_DB_DSN, 'add_api_credentials', 'user', 'pass')
        creds = await call_model_method(
            self.loop, TEST_DB_DSN, 'get_api_credentials', 'user')
        self.assertEqual('user', creds.username)
        self.assertEqual('pass', creds.password)
        self.assertEqual('', creds.description)


class DbCallTest(asynctest.TestCase):

    forbid_get_event_loop = True

    def setUp(self):
        super().setUp()
        ensure_database()
        self.config = create_test_config()

    def test_db_call_add(self):
        """db_call can add API credentials."""
        args = argparse.Namespace(
            action='add', username='user', password='pass', description='desc')
        db_call(args, self.config, loop=self.loop)
        args = argparse.Namespace(action='list')
        [creds] = db_call(args, self.config, loop=self.loop)
        self.assertEqual('user', creds.username)
        self.assertEqual('pass', creds.password)
        self.assertEqual('desc', creds.description)

    def test_db_call_list(self):
        """db_call can list API credentials."""
        args1 = argparse.Namespace(
            action='add', username='user1', password='pass1', description='')
        db_call(args1, self.config, loop=self.loop)
        args2 = argparse.Namespace(
            action='add', username='user2', password='pass2', description='')
        db_call(args2, self.config, loop=self.loop)
        args = argparse.Namespace(action='list')
        [creds1, creds2] = db_call(args, self.config, loop=self.loop)
        self.assertEqual('user1', creds1.username)
        self.assertEqual('pass1', creds1.password)
        self.assertEqual('user2', creds2.username)
        self.assertEqual('pass2', creds2.password)

    def test_db_call_remove(self):
        """db_call can remove API credentials."""
        args = argparse.Namespace(
            action='add', username='user', password='pass', description='desc')
        db_call(args, self.config, loop=self.loop)
        args = argparse.Namespace(action='remove', username='user')
        self.assertTrue(db_call(args, self.config, loop=self.loop))
        args = argparse.Namespace(action='list')
        self.assertEqual([], db_call(args, self.config, loop=self.loop))

    def test_db_call_remove_no_op(self):
        """db_call returns False if credentials are not found on removal."""
        args = argparse.Namespace(action='remove', username='user')
        self.assertFalse(db_call(args, self.config, loop=self.loop))


class PrintResultTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        ensure_database()
        self.stream = io.StringIO()

    def test_print_result_none(self):
        """If result is None, nothing is printed."""
        print_result(None, file=self.stream)
        self.assertEqual('', self.stream.getvalue())

    def test_print_result_true(self):
        """If result is True, a success message is printed."""
        print_result(True, file=self.stream)
        self.assertEqual('Action succeeded\n', self.stream.getvalue())

    def test_print_result_false(self):
        """If result is False, a no-op message is printed."""
        print_result(False, file=self.stream)
        self.assertEqual('No action performed\n', self.stream.getvalue())

    def test_print_list(self):
        """If result is a list, a table with credentials is printed."""
        credentials = [
            APICredentials('user1', 'pass1', 'desc1'),
            APICredentials('user2', 'pass2', 'desc2')]
        print_result(credentials, file=self.stream)
        output = self.stream.getvalue()
        self.assertIn('user1', output)
        self.assertIn('pass1', output)
        self.assertIn('desc1', output)
        self.assertIn('user2', output)
        self.assertIn('pass2', output)
        self.assertIn('desc2', output)


class MainTest(fixtures.TestWithFixtures):

    def setUp(self):
        super().setUp()
        tmpdir = self.useFixture(fixtures.TempDir())
        self.config_path = tmpdir.join('config.yaml')
        self.config = create_test_config(filename=self.config_path)

    @mock.patch('basic_auth.script.manage_credentials.db_call')
    def test_main(self, mock_db_call):
        """The script main performs DB operation."""
        args = ['--config', self.config_path, 'add', 'user', 'pass']
        main(raw_args=args, file=io.StringIO())
        mock_db_call.assert_called_with(mock.ANY, self.config, loop=None)