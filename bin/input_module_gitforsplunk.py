# encoding = utf-8

import os, sys, time, datetime, collections, subprocess, re

def validate_input(helper, definition):
    repo_location = definition.parameters.get('repo_location', None)
    # check folder exists
    # check its a git folder
    pass

def gitcmd(cmds, my_env, event_data):
    p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=my_env)
    o = p.communicate()
    if sys.version_info < (3, 0):
        str_stdout = str(o[0])
        str_stderr = str(o[1])
    else:
        str_stdout = o[0].decode('utf-8')
        str_stderr = o[1].decode('utf-8')
    event_data.append("COMMAND: " + " ".join(cmds) + "\n" + "OUTPUT:" + str_stdout + "\n" + str_stderr + "\n" + "EXITCODE: " + str(p.returncode))
    return p.returncode, str_stdout


def calcDirSize(start_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            total_size += os.path.getsize(os.path.join(dirpath, f))
    return total_size

def collect_events(helper, ew):
    event_data = []

    started = time.clock()
    status = 2
    try:
        SPLUNK_HOME = os.environ['SPLUNK_HOME']
        event_data.append("GitForSplunk " + str(int(time.time())))
        event_data.append("SPLUNK_HOME=" + SPLUNK_HOME)

        working_directory = os.path.join(SPLUNK_HOME, helper.get_arg('working_directory'))
        event_data.append("GIT_WORK_TREE=" + working_directory)
        os.chdir(working_directory)

        my_env = os.environ.copy()
        # this needs to be nulled out otherwise the push step will fail due to SSL libs
        my_env["LD_LIBRARY_PATH"] = ""
        # HOME needs to be nulled out becuase it can be incorrectly set to "root" if the 
        # root user spawned Splunk but then Splunk runs as a different user. git will fail 
        # becuase it can't read the root directory to get the user git settings.
        my_env["HOME"] = ""
        my_env["GIT_WORK_TREE"] = working_directory
        my_env["GIT_DIR"] = os.path.join(working_directory, helper.get_arg('repository_directory'))
        event_data.append("GIT_DIR=" + my_env["GIT_DIR"])

        if helper.get_arg('include_btool_output'):
            btool_folder_name = "btool_output"
            btool_confs = [x.strip() for x in helper.get_arg('btool_conf_files').split(',')]
            if not os.path.exists(btool_folder_name):
                os.makedirs(btool_folder_name)
            for the_file in os.listdir(btool_folder_name):
                file_path = os.path.join(btool_folder_name, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                event_data.append("Exception: " + str(e))
            for conf_type in btool_confs:
                with open(os.path.join(btool_folder_name, conf_type), "w") as log:
                    p = subprocess.Popen([os.path.join(SPLUNK_HOME, 'bin', 'splunk'), "btool", conf_type, "list", "--debug"], stdout=log, stderr=subprocess.PIPE, shell=False)
                    o = p.communicate()
                    event_data.append("Running Btool for: " + conf_type + " (rc=" + str(p.returncode) + ")")

        ret_code, ret_output = gitcmd(["git", "status"], my_env, event_data)
        if ret_code > 0:
            raise Exception("Error occured - is git installed?")
        # this can fail if the splunk user doesnt have permissions to read files or if files are locked. 
        # Could use --ignore-errors but its better to fail so someone will notice and fix it, rather than half-working.
        ret_code, ret_output = gitcmd(["git", "add", "--all"], my_env, event_data)
        if ret_code > 0:
            raise Exception("Error occured - are file permissions correct or are files locked?")

        # this command can return 1 if there are no changes.
        ret_code, ret_output = gitcmd(["git", "commit", "-m", "auto"], my_env, event_data)
        if ret_code == 1 and "nothing to commit" in ret_output:
            event_data.append("No changes")
        else:
            if ret_code > 0:
                raise Exception("Error occured")
                
            git_size = calcDirSize(my_env["GIT_DIR"])
            m = re.search(r"\s(\d+ files? changed[^\r\n]+)", ret_output)
            if not m is None:
                ret_code, ret_output = gitcmd(["git", "commit", "--amend", "-m", "Auto: " + format((git_size / 1000000),'.0f') + " MB, " + str(m.group())], my_env, event_data)

            status = 1

            ret_code, ret_output = gitcmd(["git", "log", "--stat=150,120", "-1"], my_env, event_data)

            event_data.append("repo_size=" + str(git_size))

            if helper.get_arg('remote_push'):
                ret_code, ret_output = gitcmd(["git", "push"], my_env, event_data)
                if ret_code > 0:
                    raise Exception("Error occured - is authentication to remote site correct? and network path available?")

        status = 0

    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        event_data.append(template.format(type(ex).__name__, ex.args))

    event_data.append("runtime=" + str(time.clock() - started))
    event_data.append("status=" + str(status))
    #event_data.append("sourcetype=" + helper.get_sourcetype())
    #event_data.append("source=" + helper.get_input_type())
    #event_data.append("index=" + helper.get_output_index())
    #helper.log_info("\n".join(event_data) + " !!!!! NOTE THIS ISNT THE REAL EVENT> THIS IS JUST DEBUGGING");

    event = helper.new_event(source=helper.get_input_type(), index=helper.get_output_index(), sourcetype=helper.get_sourcetype(), data="\n".join(event_data))
    
    ew.write_event(event)

