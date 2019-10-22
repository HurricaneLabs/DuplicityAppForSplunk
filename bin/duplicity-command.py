import argparse
import os
import sys

if os.uname()[0].lower() == "linux":
    arch_lib_path = "lib/linux-%s" % os.uname()[-1]
else:
    arch_lib_path = "lib/%s" % os.uname()[0].lower()

app_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(app_dir, arch_lib_path))

from duplicity import backend
from duplicity import commandline
from duplicity import diffdir
from duplicity import dup_collections
from duplicity import dup_main
from duplicity import dup_time
from duplicity import globals as dup_globals
from duplicity import gpg
from duplicity import log
from duplicity import util

from splunk import Intersplunk
from splunk.clilib.bundle_paths import make_splunkhome_path


with open(make_splunkhome_path(["etc", "auth", "splunk.secret"]), "r") as f:
    os.environ["PASSPHRASE"] = f.read().strip()


log.setup()
log._logger.handlers = []


def skip_exit(code):
    pass
log.sys.exit = skip_exit


def log_startup_parms(verbosity=log.INFO):
    pass
dup_main.log_startup_parms = log_startup_parms


def main():
    output = []

    def Log(s, verb_level, code=1, extra=None, force_print=False):
        if verb_level <= log.getverbosity():
            output.extend(s.split("\n"))

    # def PrintCollectionStatus(col_stats, force_print=False):
    #     # raise ValueError(type(col_stats.matched_chain_pair[1]))
    #     output.append({
    #         "num_backup_sets":
    #     })

    # log.PrintCollectionStatus = PrintCollectionStatus

    results = None
    try:
        settings = dict()
        Intersplunk.readResults(None, settings, True)

        dup_time.setcurtime()

        archive_dir = os.path.join(app_dir, "local", "data", "archive")

        try:
            os.makedirs(archive_dir)
        except:
            pass

        if sys.argv[1] == "splunk-last-backups":
            ap = argparse.ArgumentParser()
            ap.add_argument("--time", type=int)
            ap.add_argument("backend")
            args = ap.parse_args(sys.argv[2:])

            dup_globals.gpg_profile = gpg.GPGProfile()
            dup_globals.gpg_profile.passphrase = os.environ["PASSPHRASE"]

            backend.import_backends()

            dup_globals.backend = backend.get_backend(args.backend)

            if dup_globals.backup_name is None:
                dup_globals.backup_name = commandline.generate_default_backup_name(args.backend)

            commandline.set_archive_dir(archive_dir)

            results = []
            time = args.time
            col_stats = dup_collections.CollectionsStatus(dup_globals.backend,
                                                          dup_globals.archive_dir_path,
                                                          "list-current").set_values()

            try:
                sig_chain = col_stats.get_backup_chain_at_time(time)
            except dup_collections.CollectionsError:
                results.append({
                    "last_full_backup_time": 0,
                    "last_incr_backup_time": 0,
                })
            else:
                if sig_chain.incset_list:
                    last_incr_backup_time = max([incset.end_time for incset in sig_chain.incset_list])
                else:
                    last_incr_backup_time = 0

                results.append({
                    "last_full_backup_time": col_stats.get_last_full_backup_time(),
                    "last_incr_backup_time": last_incr_backup_time
                })
        elif sys.argv[1] == "splunk-file-list":
            ap = argparse.ArgumentParser()
            ap.add_argument("--time")
            ap.add_argument("backend")
            args = ap.parse_args(sys.argv[2:])
            args.time = int(args.time.split(".")[0])

            dup_time.setcurtime(args.time)
            dup_globals.restore_time = args.time

            dup_globals.gpg_profile = gpg.GPGProfile()
            dup_globals.gpg_profile.passphrase = os.environ["PASSPHRASE"]

            backend.import_backends()

            dup_globals.backend = backend.get_backend(args.backend)

            if dup_globals.backup_name is None:
                dup_globals.backup_name = commandline.generate_default_backup_name(args.backend)

            commandline.set_archive_dir(archive_dir)

            results = []
            col_stats = dup_collections.CollectionsStatus(dup_globals.backend,
                                                          dup_globals.archive_dir_path,
                                                          "list-current").set_values()

            time = args.time
            sig_chain = col_stats.get_signature_chain_at_time(time)

            path_iter = diffdir.get_combined_path_iter(sig_chain.get_fileobjs(time))
            for path in path_iter:
                if path.difftype != u"deleted" and path.index:
                    mode = bin(path.mode)[2:]

                    perms = ""
                    for p, val in enumerate(mode):
                        if p in (0, 3, 6):
                            c = "r"
                        elif p in (1, 4, 7):
                            c = "w"
                        elif p in (2, 5, 8):
                            c = "x"

                        perms += c if int(val) else "-"

                    if path.type == "dir":
                        perms = "d" + perms
                    elif path.type == "sym":
                        perms = "l" + perms
                    else:
                        perms = "-" + perms

                    results.append({
                        "perms": perms,
                        "owner": path.stat.st_uid,
                        "group": path.stat.st_gid,
                        "size": path.stat.st_size,
                        "modtime": path.stat.st_mtime,
                        "filename": os.path.join(*path.index),
                    })
        else:
            args = ["--archive-dir", archive_dir] + sys.argv[1:]
            action = commandline.ProcessCommandLine(args)

            log.Log = Log
            try:
                dup_main.do_backup(action)
            except dup_collections.CollectionsError:
                results = []
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        # sys.stderr.write(traceback.format_exc())

        Intersplunk.generateErrorResults(
            "Traceback: %s" % traceback.format_exc()
        )

        return

    if output and not results:
        import time

        results = [{
            "_raw": "\n".join(output),
            "_time": time.time()
        }]

    if results:
        try:
            Intersplunk.outputResults(results)
        except Exception:
            import traceback
            sys.stderr.write(traceback.format_exc())
            results = Intersplunk.generateErrorResults(
                "Traceback: %s" % traceback.format_exc()
            )
            Intersplunk.outputResults(results)



if __name__ == "__main__":
    main()
