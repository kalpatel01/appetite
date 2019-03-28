#!/usr/bin/env
# pylint: disable=invalid-name,no-self-use,missing-returns-doc,missing-type-doc
"""Appetite test

Unit test to externally test the internal functionality and logic of appetite.
This does not test ssh or repo calls.
"""

import os
import sys
import subprocess # nosec
import unittest
import shutil
import shlex
import json

MAX_THREADS = 1
SILENT = False

REPO_BASE_FOLDER = "repo"

TEST_PATH = os.path.dirname(os.path.realpath(__file__))
SCRIPT_PATH = TEST_PATH.replace('/tests', '/src')

LOG_DIR = os.path.join(TEST_PATH, '.test_log')
TMP_DIR = os.path.join(TEST_PATH, REPO_BASE_FOLDER, 'tmp')
META_DIR = os.path.join(TEST_PATH, REPO_BASE_FOLDER, 'meta')
LOG_FILE = os.path.join(LOG_DIR, 'appetite_repo.log')


def get_python_path():
    """Finds python path, useful when using IDEs testing different versions of python
    :return: None
    """
    split_lib = os.__file__.split("/lib/")
    if len(split_lib) < 2:
        # Use default
        return ""
    return "%s/bin/" % split_lib[0]


PYTHON_BIN_LOCATION = get_python_path()

# Test hostnames that match deploymentmethods and commands
TEST_HOST_LIST = [
    "splunk-lm001-0c",
    "splunk-cm001-0c",
    "splunk-ds001-0c",
    "splunk-idx001-0c",
    "splunk-idx002-0c",
    "splunk-idx003-0c",
    "splunk-idx001-1c",
    "splunk-idx002-1c",
    "splunk-idx003-1c",
    "splunk-sha001-0c",
    "splunk-shm001-0c",
    "splunk-dcm001-0c",
    "splunk-scm001-0c",
    "splunk-scm002-0c",
    "splunk-scm003-0c",
    "splunk-scs001-0c"
]

def set_command_cmd(ext_args=""):
    # Create the base command to run test against

    if 'config-file' not in ext_args:
        ext_args += "--config-file ../configs/demo_splunk/repo_test.conf "

    return shlex.split("%s"
                       "python appetite.py "
                       "--logging-path %s "
                       "--hosts %s %s" %
                       (PYTHON_BIN_LOCATION,
                        LOG_DIR,
                        " ".join(TEST_HOST_LIST),
                        ext_args))


COMMON_CMD = set_command_cmd()

def cmd_appetite(manifest, extra_params, num_threads=1, delete_logs=False):
    """Run appetite with defined params
    :param manifest: manifest to reference
    :param extra_params: extra params if needed
    :param num_threads: Number of threads to use
    :param delete_logs: Delete logs before running
    :return: output from appetite call
    """

    if delete_logs:
        delete_log_dir()
    create_log()

    cmd = list(COMMON_CMD) + shlex.split("--num-conns %s --apps-manifest %s %s%s" % (
        num_threads, manifest, "--silent " if SILENT else "", extra_params))

    return subprocess.check_call(cmd, cwd=SCRIPT_PATH, shell=False) # nosec


def create_log():
    """Crete log path and starting file"""

    if not os.path.isfile(LOG_FILE):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        with open(LOG_FILE, 'a') as touch:
            touch.write("")


def delete_log_dir():
    """Delete current test logs"""

    delete_path(LOG_DIR)


def clean_tmp_folders():
    """Delete tmp directories"""

    delete_log_dir()
    delete_path(TMP_DIR)
    delete_path(META_DIR)
    delete_file("appetite_lock")


def delete_path(path):
    """Delete current path"""
    try:
        if os.path.exists(path):
            shutil.rmtree(path)
    except Exception as e:
        raise Exception("Problem deleting folder; path: %s error: %s" % (LOG_DIR, e.message))


def delete_file(file_path):
    """Delete file"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        raise Exception("Problem deleting file; path: %s error: %s" % (LOG_DIR, e.message))


def get_entry(*args):
    """Find strings with in logs"""

    results = find_entry(LOG_FILE, *args)

    if not results:
        return

    try:
        # Log files produced are in json format
        return json.loads(results)
    except Exception as e:
        print "line: %s" % str(results)
        print e.message
        raise


def find_entry(filepath, *args):
    """Find strings in files"""

    with open(filepath, 'r+') as f:
        for line in f:
            if next((False for str_input in args if str_input not in line), True):
                return line
    return


class Test01BasicAppetiteRun(unittest.TestCase):
    """ Tests that need a single appetite run to verify
    """

    def test_00_test_full_run(self):
        """Run a full install with clean systems

        If a system is new then firstrun has to be enabled and if needed templating
        """
        clean_tmp_folders()

        cmd_appetite("manifest_00_fullinstall.csv",
                     " --firstrun --templating", 1, True)

    def test_01_test_full_run_threaded(self):
        """Run a full install with threading

        Using a thread pool to run app installs
        """

        if MAX_THREADS > 1:
            clean_tmp_folders()

            cmd_appetite("manifest_00_fullinstall.csv",
                         " --firstrun --templating", MAX_THREADS, True)

    def test_02_check_templating(self):
        """Checks for templating"""

        app_location = os.path.join(TEST_PATH, "repo/tmp/hosts/splunk-cm001-0c/etc/apps/App02/App02.txt")

        # Check if value was filtered using the test/filters/example.py and comes from a config yml file
        self.assertIsNotNone(find_entry(app_location, 'text_has_been_filtered'))

        # Check if value comes from a config file (json on the command line)
        self.assertIsNotNone(find_entry(app_location, 'searchforthis'))

    def test_03_global_override(self):
        """Checks global override"""

        removed_file = "FileThatWillGloballyKillEverything.txt"
        global_msg = "Globally these files should not exist in the App"
        log_msg = '"app": "App%s", "files": ["%s/%s"], "hostname": "splunk-%s001-0c", "msg": "%s'


        for server in ['cm', 'ds']:
            for app_num in ['01', '02']:
                file_location = os.path.join(TEST_PATH,
                                             "repo/tmp/hosts/splunk-%s001-0c/etc/apps/App%s/default/" % (server, app_num),
                                             removed_file)

                self.assertFalse(os.path.isfile(file_location))
                self.assertIsNotNone(get_entry(log_msg % (app_num, 'default', removed_file, server, global_msg)))


    def test_04_install_splunk(self):
        """Checks install splunk"""

        splunk_install_file = "splunk_installed.txt"
        untemplated_value = "{{ nothing_happened_here }}"

        file_location = os.path.join(TEST_PATH, "repo/tmp/hosts/splunk-cm001-0c/",
                                     splunk_install_file)

        self.assertTrue(os.path.isfile(file_location))
        self.assertIsNotNone(find_entry(file_location, untemplated_value))

    def test_05_test_no_change_found(self):
        """Run the same manifest therefore no changes are found"""

        # Run second time
        cmd_appetite("manifest_00_fullinstall.csv",
                     "", MAX_THREADS, True)

        appetite_stats = get_entry("Appetite complete")

        self.assertFalse(appetite_stats['log']['changes'])

class Test02AppetiteStateChecks(unittest.TestCase):
    """ Tests that require multiple runs of Appetite to verify
    """

    def test_00_multiple_appetite_runs01(self):
        """Clean appetite run"""

        clean_tmp_folders()

        cmd_appetite("manifest_00_fullinstall.csv",
                     " --firstrun --templating", MAX_THREADS)

    def test_01_multiple_appetite_runs02(self):
        """Run appetite with state change manifest """

        cmd_appetite("manifest_01.csv",
                     "", MAX_THREADS, True)

    def test_02_find_dups(self):
        """Check for dups"""

        # Should find 2 occurances of shm
        shm = get_entry("Dup app found", "splunk-shm")['log']
        self.assertEquals(shm['app_info']['app'], "App01")
        self.assertEquals(shm['occurences'], 2)

        # Should find 3 occurances of sha
        sha = get_entry("Dup app found", "splunk-sha")['log']
        self.assertEquals(sha['app_info']['app'], "App01")
        self.assertEquals(sha['occurences'], 3)

    def test_03_look_for_deleted_app(self):
        """Test deletion of apps"""

        delete_stat = get_entry('"msg": "delete"')['log']

        self.assertIn("/opt/splunk/etc/slave-apps/App04", delete_stat['cmd'])

    def test_04_changes(self):
        """Look for app changes"""

        file_location = os.path.join(TEST_PATH,
                                     "repo/tmp/hosts/splunk-ds001-0c/etc/deployment-apps/App06/new_file.txt")

        changes_found = get_entry('"msg": "Changes found"', "splunk-ds", '"app": "App06"')['log']

        self.assertTrue(changes_found)
        self.assertTrue(os.path.isfile(file_location))

if __name__ == '__main__':
    unittest.main()
