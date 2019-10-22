import json
import os
import shlex
import sys
import tempfile

if os.uname()[0].lower() == "linux":
    arch_lib_path = "lib/linux-%s" % os.uname()[-1]
else:
    arch_lib_path = "lib/%s" % os.uname()[0].lower()

script_dir = os.path.abspath(os.path.dirname(__file__))

app_dir = os.path.normpath(os.path.join(script_dir, ".."))
sys.path.insert(0, os.path.join(app_dir, arch_lib_path))

from duplicity import commandline, dup_main, dup_time, log

# from splunk.clilib.bundle_paths import make_splunkhome_path
from splunklib.modularinput import Argument, Event, Scheme, Script


def make_splunkhome_path(path_parts):
    pth = ["$SPLUNK_HOME"] + path_parts
    return os.path.expandvars(os.path.join(*pth))


with open(make_splunkhome_path(["etc", "auth", "splunk.secret"]), "r") as f:
    os.environ["PASSPHRASE"] = f.read().strip()


log.setup()

def skip_exit(code):
    pass
log.sys.exit = skip_exit


def log_startup_parms(verbosity=log.INFO):
    pass
dup_main.log_startup_parms = log_startup_parms


class Duplicity(Script):
    def get_scheme(self):
        # Returns scheme.
        scheme = Scheme("Duplicity Backup")
        scheme.description = "Runs a Splunk backup"

        arg = Argument("target_url")
        arg.data_type = Argument.data_type_string
        arg.description = "Backup destination"
        arg.required_on_create = False
        scheme.add_argument(arg)

        arg = Argument("full_if_older_than")
        arg.data_type = Argument.data_type_string
        arg.description = "Max time between full backups"
        arg.required_on_create = False
        scheme.add_argument(arg)

        arg = Argument("extra_duplicity_args")
        arg.data_type = Argument.data_type_string
        arg.description = "Additional arguments to pass to duplicity"
        arg.required_on_create = False
        scheme.add_argument(arg)

        arg = Argument("whitelist")
        arg.data_type = Argument.data_type_string
        arg.description = "Duplicity whitelist"
        arg.required_on_create = False
        scheme.add_argument(arg)

        arg = Argument("blacklist")
        arg.data_type = Argument.data_type_string
        arg.description = "Duplicity blacklist"
        arg.required_on_create = False
        scheme.add_argument(arg)

        return scheme

    def validate_input(self, validation_definition):
        # Validates input.
        pass

    def stream_events(self, inputs, ew):
        # Splunk Enterprise calls the modular input,
        # streams XML describing the inputs to stdin,
        # and waits for XML on stdout describing events.

        try:
            output = []

            def Log(s, verb_level, code=1, extra=None, force_print=False):
                if verb_level <= 5:
                    for line in s.split("\n"):
                        output.append(line)

            (backup_name, config) = inputs.inputs.popitem()

            config_to_arg = {
                "full_if_older_than": ("--full-if-older-than", "30D")
            }

            params = {}
            for conf_opt in config_to_arg:
                (_, default) = config_to_arg[conf_opt]
                if default is not None:
                    params[conf_opt] = default

            for conf_opt in config:
                if conf_opt not in config_to_arg:
                    continue
                params[conf_opt] = config[conf_opt]

            args = []
            for (param, value) in params.items():
                (arg, _) = config_to_arg[param]
                if value is True:
                    args.append(arg)
                elif value:
                    args.extend((arg, value))

            if "extra_duplicity_args" in config:
                args.extend(shlex.split(config["extra_duplicity_args"]))

            archive_dir = os.path.join(app_dir, "local", "data", "archive")
            backup_base_dir = make_splunkhome_path(["etc"])
            # archive_dir_relative = archive_dir[len(backup_base_dir) + 1:]

            try:
                os.makedirs(archive_dir)
            except:
                pass

            if config.get("whitelist"):
                whitelist_file = tempfile.NamedTemporaryFile()

                with open(whitelist_file.name, "w") as f:
                    for entry in config["whitelist"].split(";"):
                        entry = os.path.expandvars(entry)
                        f.write("%s\n" % entry)

                args.extend(("--include-filelist", whitelist_file.name))

            if config.get("blacklist"):
                blacklist_file = tempfile.NamedTemporaryFile()

                with open(blacklist_file.name, "w") as f:
                    for entry in config["blacklist"].split(";"):
                        entry = os.path.expandvars(entry)
                        f.write("%s\n" % entry)

                args.extend(("--exclude-filelist", blacklist_file.name))

            args.extend(["--exclude", archive_dir])
            args.extend(["--archive-dir", archive_dir])
            args.append(backup_base_dir)
            args.append(config["target_url"])

            dup_time.setcurtime()
            action = commandline.ProcessCommandLine(args)
            log.Log = Log
            dup_main.do_backup(action)

            event = {}

            in_stats = False
            for line in output:
                line = line.strip()
                if line.startswith("---"):
                    if in_stats:
                        break
                    elif "Backup Statistics" in line:
                        in_stats = True

                    continue
                elif not in_stats:
                    continue

                key, value = line.split(" ")[:2]
                event[key] = value

            ew.write_event(Event(
                data=json.dumps(event),
                sourcetype="duplicity"
            ))
        except:
            import traceback
            sys.stderr.write("%s\n" % traceback.print_exc())


if __name__ == "__main__":
    sys.exit(Duplicity().run(sys.argv))
