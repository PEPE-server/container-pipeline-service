from os import path, getcwd, chdir, system

from yaml import load

from DependencyValidation import ContainerDependencyGraph
from NutsAndBolts import GlobalEnvironment, execute_command
from Summary import SummaryCollector


class Validator(object):
    def __init__(self):
        self._success = True
        self._summary_collector = None
        pass

    @staticmethod
    def _load_yaml(file_name):
        """Loads yaml data into an object and returns it"""
        with open(file_name, "r") as ymlfile:
            return load(ymlfile)

    def run(self):
        """"Runs the validator. returning True or False based on success or failure"""
        raise NotImplementedError("Implement this method")


class IndexValidator(Validator):
    """Top level class for validators"""

    def __init__(self, index_file=None):
        Validator.__init__(self)
        self._file_name = path.basename(index_file)
        self._index_file = index_file
        self._yaml = self._load_yaml(self._index_file)["Projects"]
        self._status_list = {
            "fail": [],
            "success": []
        }

    def _mark_entry_invalid(self, entry):
        self._success = False
        if entry in self._status_list["success"]:
            self._status_list["success"].remove(entry)
        if entry not in self._status_list["fail"]:
            self._status_list["fail"].append(entry)

    def _mark_entry_valid(self, entry):
        if entry not in self._status_list["success"]:
            self._status_list["success"].append(entry)

    def run(self):
        """Runs the IndexValidator, returning True or False based on success or failure"""
        raise NotImplementedError("Implement this method.")


class IndexFormatValidator(IndexValidator):
    """Checks the format of index files"""

    def __init__(self, index_file):

        IndexValidator.__init__(self, index_file)

    def run(self):

        id_list = []

        for entry in self._yaml:

            self._summary_collector = SummaryCollector(self._file_name, entry)
            self._mark_entry_valid(entry)

            # Check if id field exists
            if "id" not in entry or ("id" in entry and entry["id"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing id")

            else:
                # Check if id has not already been passed
                if entry["id"] in id_list:
                    self._mark_entry_invalid(entry)
                    self._summary_collector.add_error("id field must be unique in the file")

                else:
                    id_list.append(entry["id"])

            # Checking app-id field
            if "app-id" not in entry or ("app-id" in entry and entry["app-id"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing app-id")

            else:
                if entry["app-id"] != self._file_name.split(".")[0]:
                    self._mark_entry_invalid(entry)
                    self._summary_collector.add_error("app-id should be same as first part of the file name")

                if "_" in entry["app-id"] or "/" in entry["app-id"] or "." in entry["app-id"]:
                    self._mark_entry_invalid(entry)
                    self._summary_collector.add_error("app-id cannot contain _, / or . character.")

            # Checking job-id field
            if "job-id" not in entry or ("job-id" in entry and entry["job-id"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing job-id field")

            else:
                if "_" in entry["job-id"] or "/" in entry["job-id"] or "." in entry["job-id"]:
                    self._mark_entry_invalid(entry)
                    self._summary_collector.add_error("job-id cannot contain _, / or . character.")

            # Check for git-url
            if "git-url" not in entry or ("git-url" in entry and entry["git-url"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing git-url")

            # Checking git-path
            if "git-path" not in entry or ("git-path" in entry and entry["git-path"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing git-path")

            # Check git-branch
            if "git-branch" not in entry or ("git-branch" in entry and entry["git-branch"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing git-branch")

            # Check target-file
            if "target-file" not in entry or ("target-file" in entry and entry["target-file"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing target-file")

            # Check desired-tag
            if "desired-tag" not in entry or ("desired-tag" in entry and entry["desired-tag"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing desired-tag")

            # Check notify-email
            if "notify-email" not in entry or ("notify-email" in entry and entry["notify-email"] is None):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing notify-email")

            # Check depends-on
            if "depends-on" not in entry:
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing depends-on")

        return self._success, self._status_list


class IndexProjectsValidator(IndexValidator):
    """Does deeper analysis of index, checking for correctness of provided values."""

    def __init__(self, index_file):

        IndexValidator.__init__(self, index_file)

    @staticmethod
    def update_git_url(git_url, git_branch):

        clone_path = None

        # Work out the path to clone repo to
        clone_to = git_url

        if ":" in clone_to:
            clone_to = clone_to.split(":")[1]

        clone_to = GlobalEnvironment.environment.repo_dump + "/" + clone_to

        # If the path doesnt allready exist, attempt to clone repo
        if not path.exists(clone_to):
            cmd = ["git", "clone", git_url, clone_to]

            if not execute_command(cmd):
                return None

        # Update repo
        get_back = getcwd()
        chdir(clone_to)

        cmd = "git branch -r | grep -v '\->' | while read remote; do git branch --track \"${remote#origin/}\"" \
              " \"$remote\" &> /dev/null; done"

        # Get all the branches
        system(cmd)

        # fetch the branches
        cmd = ["git", "fetch", "--all"]
        execute_command(cmd)

        # Pull for update
        cmd = ["git", "pull", "--all"]
        execute_command(cmd)

        # Checkout required branch
        cmd = ["git", "checkout", "origin/" + git_branch]

        if execute_command(cmd):
            clone_path = clone_to

        chdir(get_back)

        return clone_path

    def run(self):

        container_names = {}

        for entry in self._yaml:
            self._mark_entry_valid(entry)
            self._summary_collector = SummaryCollector(self._file_name, entry)

            clone_path = self.update_git_url(entry["git-url"], entry["git-branch"])

            if clone_path is None:
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error(
                    "Could not clone specified git-url or could not find specified branch")
                continue

            # Else clone was success, check the git path
            git_path = clone_path + "/" + entry["git-path"]

            # Check if specified path exists
            if not path.exists(git_path):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("The specified git-path does not exist in git repo.")
                continue

            # Else, continue with remaining checks
            cccp_yml_path = None

            # * Check if cccp.yml file exists

            for item in ["cccp.yml", ".cccp.yml", "cccp.yaml", ".cccp.yaml"]:
                check_path = git_path + "/" + item
                if path.exists(check_path):
                    cccp_yml_path = check_path
                    break

            if cccp_yml_path is None:
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("Missing cccp yml file, please check your git-path")
                continue

            # * Check for duplicate entry for same container name
            container_name = entry["app-id"] + "/" + entry["job-id"] + ":" + str(entry["desired-tag"])
            if container_name in container_names:
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error(
                    "Duplicate entry exists at ids : " + str(container_names[container_name]))

            else:
                container_names[container_name] = []

            container_names[container_name].append(entry["id"])

            # * Check for existence of target-file
            if not path.exists(git_path + "/" + entry["target-file"]):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("The specified target-file does not exist at the git-path")

            # * Validate the cccp yaml file
            self._cccp_yaml_check(git_path, cccp_yml_path, entry)

        return self._success, self._status_list

    def _cccp_yaml_check(self, git_path, cccp_yaml_path, entry):
        """Validates the cccp yaml file"""

        cccp_yaml = self._load_yaml(cccp_yaml_path)
        self._entry_valid = True

        get_back = getcwd()
        chdir(git_path)
        # * Check for job-entry_id
        if "job-id" not in cccp_yaml:
            self._mark_entry_invalid(entry)
            self._summary_collector.add_error("Missing job-id field in cccp yaml")

        # * Check for test-skip
        if "test-skip" in cccp_yaml:
            value = cccp_yaml["test-skip"]

            try:
                if value and (value is True or value is False):
                    pass
                if value is None:
                    self._summary_collector.add_warning("Optional test-skip is set None, which means its value will be"
                                                        " ignored")
            except Exception:
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("test-skip should either be True or False as it is a flag")

        # * Check test-script
        if "test-script" in cccp_yaml:
            self._summary_collector.add_warning("Custom test-script has been specified")
            value = cccp_yaml["test-script"]
            if value and not path.exists(str(value)):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("The specified test-script does not exist")
            if value is None:
                self._summary_collector.add_warning("Optional test-script has a value of None, which means it will be"
                                                    " ignored")

        # * Check build-script
        if "build-script" in cccp_yaml:
            self._summary_collector.add_warning("Custom build-script has been specified")
            value = cccp_yaml["build-script"]
            if value and not path.exists(str(value)):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("The specified build-script does not exist")
            if value is None:
                self._summary_collector.add_warning("Optional build-script has has a value None, which means it will be"
                                                    " ignored")

        # * Check delivery-script
        if "delivery-script" in cccp_yaml:
            self._summary_collector.add_warning("Custom delivery-script has been specified.")
            value = cccp_yaml["delivery-script"]
            if value and not path.exists(str(value)):
                self._mark_entry_invalid(entry)
                self._summary_collector.add_error("The specified delivery-script does not exist")
            if value is None:
                self._summary_collector.add_warning("Optional delivery script has value None, which means it will be"
                                                    " ignored")

        chdir(get_back)


class DependencyValidator(object):
    """Does the container dependency validation."""

    dependency_graph = ContainerDependencyGraph()

    @staticmethod
    def is_dependency_acyclic():
        """Check is the dependency graph is acyclic."""
        return DependencyValidator.dependency_graph.has_no_cycles()


class DependencyValidationUpdater(IndexValidator):
    """This script reads the index file and updates the dependency graph, created nodes and edges, for containers and
    dependencies respectively."""

    def __init__(self, index_file):
        """Initialize the validator"""

        IndexValidator.__init__(self, index_file)

    def run(self):
        """Run the validator the read the index and update the dependency graph"""

        for entry in self._yaml:
            # Form the container name from index yaml
            primary_container_name = entry["app-id"] + "/" + entry["job-id"] + ":" + entry["desired-tag"]
            # Add the container to dependency graph (if it does not already exist)
            DependencyValidator.dependency_graph.add_container(primary_container_name, from_index=True)
            # Check if entry has any dependencies to account for
            if entry["depends-on"]:
                if not isinstance(entry["depends-on"], list):
                    value = [entry["depends-on"]]
                else:
                    value = entry["depends-on"]
                for item in value:
                    if ":" not in item:
                        item += ":latest"
                    # Add the dependent container to dependency graph, if it does not already exist
                    DependencyValidator.dependency_graph.add_container(str(item), from_index=True)
                    # Ensure that the dependency from current depends-on container and the current container is
                    #  established
                    DependencyValidator.dependency_graph.add_dependency(str(item), primary_container_name)
                    clone_path = None
            # Work out the path to targetfile
            git_branch = entry["git-branch"]
            target_file_dir = entry["git-url"]
            git_path = entry["git-path"]
            if ":" in target_file_dir:
                # If the git-url containers :, then we dont need the protocol part, so just get the uri
                target_file_dir = target_file_dir.split(":")[1]
            # The final git-path would be path where all repos are dumped + the git-url part + git-path
            # Example : repo_dump = /mydir, git-url = https://github.com/user/repo, git-path= /mydir
            # then final path = /mydir/github.com/user/repo/mydir
            target_file_dir = GlobalEnvironment.environment.repo_dump + "/" + target_file_dir
            target_file = target_file_dir + "/" + git_path + "/" + entry["target-file"]
            get_back = getcwd()
            chdir(target_file_dir)
            # Checkout required branch
            cmd = ["git", "checkout", "origin/" + git_branch]
            execute_command(cmd)
            chdir(get_back)
            base_image = None
            try:
                with open(target_file, "r") as f:
                    for line in f:
                        l = line.strip()
                        if l.startswith("FROM"):
                            base_image = l.split()[1]
                            break
            except Exception as e:
                print e
            if base_image:
                DependencyValidator.dependency_graph.add_container(container_name=base_image,
                                                                   from_targetfile=True)
                DependencyValidator.dependency_graph.add_dependency(base_image, primary_container_name)
        return True


class LightWeightValidator(IndexValidator):
    """Light weight validator does minimum validation, and focuses mostly on building dependency graph"""

    def __init__(self, index_file):
        IndexValidator.__init__(self, index_file)

    def run(self):
        for entry in self._yaml:
            self._summary_collector = SummaryCollector(self._file_name, entry)
            if "git-url" not in entry or "git-branch" not in entry or "git-path" not in entry or "target-file" not in \
                    entry:
                self._summary_collector.add_error("Missing git-url, git-path, git-branch or target-file")
                self._success = False
                continue
            clone_location = IndexProjectsValidator.update_git_url(entry["git-url"], entry["git-branch"])
            if not clone_location:
                self._summary_collector.add_error("Unable to clone specified git-url or find specified git-branch")
                self._success = False
                continue
            validation_path = clone_location + "/" + entry["git-path"] + "/" + entry["target-file"]
            if not path.exists(validation_path):
                self._summary_collector.add_error("Invalid git-path or target-file specified")
                self._success = False

        if self._success:
            DependencyValidationUpdater(index_file=self._index_file).run()
        return self._success
