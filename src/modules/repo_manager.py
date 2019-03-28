#!/usr/bin/env python
#pylint: disable=relative-import,too-many-instance-attributes,missing-type-doc,invalid-name
"""RepoManager

Handle function associated with the appetite repository.
"""
import os
import helpers
import consts
import logger

DEBUG = False

COMMIT_KEYS = {
    'commit_id': "%H",
    'abbrv_commit_id': "%h",
    'author_name': "%an",
    'author_email': "%ae",
    'committer_name': "%cn",
    'committer_email': "%ce",
    'subject': "%s",
    'body': "%b",
    'commit_notes': "%N"
}


class RepoManager(object):
    """Main class to handle appetite repos
    """
    def __init__(self, _reponame, _repo_url, _repo_branch,
                 _repo_path, _scratch_folder, _manifest):
        """Repo Manager init
        :param _reponame: Name of repo
        :param _repo_url: URL of repo
        :param _repo_branch: Repo branch
        :param _repo_path: Local location of repo
        :param _scratch_folder: Abs path of scratch folder
        :param _manifest: Manifest to monitor and parse
        """
        self.paths = {
            'scratch_path': _scratch_folder,
            'absolute_path': os.path.join(_scratch_folder, _repo_path)
        }

        self.paths['repo_path'] = os.path.join(self.paths['absolute_path'],
                                               _reponame)
        self.paths['manifest_repo'] = os.path.join(self.paths['repo_path'],
                                                   consts.CONFIG_PATH_NAME,
                                                   _manifest)

        self.manifest = _manifest
        self.url = _repo_url
        self.branch = _repo_branch

        self.track = helpers.get_track()

        self.project = ""
        self.reponame = ""
        self.prev_commit = ""

        repo_split = _repo_url.split('/')
        if len(repo_split) > 1:
            self.project = repo_split[-2]
            self.reponame = repo_split[-1].split('.')[0]

    def pull_repo(self, force=False):
        """Clone repo to specified dir.  Delete repo if it currently exist unless reuse.
        """
        try:
            helpers.create_path(self.paths['absolute_path'], True)

            if force:
                self.delete_repo()

            if not os.path.exists(self.paths['repo_path']):
                logger.info("Starting Repo Cloning", track=self.track)

                output, rc = helpers.run(
                    "git clone -b %s %s" % (self.branch, self.url),
                    self.paths['absolute_path'])

                if rc > 0:
                    self.delete_repo()
                    logger.error("Pulling_repo", error=output, path=self.paths['repo_path'])
                    return -1
                return 1
            else:
                return 0
        except Exception as e:
            logger.errorout("Pulling_repo", err_msg=e.message,
                            error="Error pulling repo", path=self.paths['repo_path'])

    def run_command(self, cmd):
        """Run command on repo directory
        """
        return helpers.run(cmd, self.paths['repo_path'])

    def get_checkout_id(self, commit_id=None):
        """Generate the checkout id
        """

        return commit_id if commit_id else self.branch

    def checkout_commit_id(self, commit_id=None):
        """Checks out the commit id for the repo
        """

        checkout_id = self.get_checkout_id(commit_id)

        response = {"output": "",
                    "rc": 0,
                    "cmd": "git checkout {0}".format(checkout_id),
                    "checkout_id": self.get_checkout_id(commit_id)}

        # Already checked out
        if self.prev_commit == checkout_id:
            return response

        output, rc = self.run_command(response['cmd'])

        response["output"] = output
        response["rc"] = rc

        return response

    def set_commit_id(self, commit_id=None, _level=0):
        """Checks out and check the commit id for the repo
        """

        response = self.checkout_commit_id(commit_id)

        if response["rc"] > 0 and _level < 1:
            # Corrupted checkout state, try to recover
            logger.warn("Possible corrupted checkout state", desc="Problem with checkout", error=response["output"],
                        commit_id=response["checkout_id"], path=self.paths['repo_path'],
                        cmd=response["cmd"], recursion_level=_level,
                        track=self.track)

            # Want to guarantee that the branch is completely reset.
            git_reset_output, rc = self.run_command("git reset --hard {0}".format(self.branch)) #pylint: disable=unused-variable

            if rc < 1:
                # Clean up git so there are no untracked files.
                self.run_command("git clean -fd")

            self.set_commit_id(commit_id, _level+1)

        if response["rc"] > 0:
            logger.errorout("set_commit_id", desc="Problem setting commit id", error=response["output"],
                            commit_id=response["checkout_id"], path=self.paths['repo_path'],
                            cmd=response["cmd"], recursion_level=_level,
                            track=self.track)

        self.prev_commit = response["checkout_id"]

        return True

    def get_commit_log(self, commit_id=None):
        """Get the current commit log
        """
        try:
            log_object = {}
            for key, value in COMMIT_KEYS.items():
                git_command = ['git', 'log', '-1', '--pretty=\'%s\'' % value]
                if commit_id:
                    git_command.insert(2, commit_id)

                stdout, _rc = helpers.run(git_command,
                                          self.paths['repo_path'])

                output = helpers.filter_content(stdout)
                if key in consts.RENAME_COMMIT_LOG_KEYS:
                    key = consts.RENAME_COMMIT_LOG_KEYS[key]
                log_object[key] = output

            log_object['project'] = self.project
            log_object['reponame'] = self.reponame

            return log_object
        except Exception as e:
            logger.errorout("get_commit_log", error="Problem getting commit log",
                            error_msg=e.message, track=self.track)

    def check_for_update(self, dry_run=False):
        """Checks for updates to the repo and if the manifest has changed
        """
        self.set_commit_id()

        # If dry run do not pull from external repo
        stdout, _rc = helpers.run(
            "git pull",
            self.paths['repo_path'],
            dry_run)

        manifest_found = next((True for manifest_file in self.manifest if manifest_file in stdout), False)

        commit_log = self.get_commit_log()
        self.track["push_commit_id"] = commit_log['app_commit_id']
        self.track["push_abbrev_commit_id"] = commit_log['app_abbrev_commit_id']

        filtered_output = helpers.filter_content(stdout)

        return {'triggered': manifest_found, 'output': filtered_output}

    def delete_repo(self):
        """Deletes repo
        """
        logger.info('delete', path=self.paths['repo_path'], track=self.track)
        helpers.delete_path(self.paths['repo_path'])
