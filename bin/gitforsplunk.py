#!/usr/bin/env python
#
# rewrite by Chris and Gemini to remove all external dependencies splunklib and addon builder.
# backwards compatable with historical versions


import sys
import os
import shutil
import subprocess
import traceback
import xml.etree.ElementTree as ET
import time
import re
import glob
import hashlib

SCHEME_XML = """<scheme>
    <title>Git for Splunk</title>
    <description>Automate Git versioning and backups for Splunk configuration files.</description>
    <use_external_validation>false</use_external_validation>
    <streaming_mode>xml</streaming_mode>
    <endpoint>
        <args>
            <arg name="working_directory">
                <title>Working Directory</title>
                <description>This is the path which will be tracked for changes. Relative to SPLUNK_HOME or an absolute path</description>
                <data_type>string</data_type>
                <required_on_create>true</required_on_create>
                <required_on_edit>true</required_on_edit>
            </arg>
            <arg name="repository_directory">
                <title>Repository Directory</title>
                <description>The path where the git repository will be stored. Relative to the working directory or an absolute path.</description>
                <data_type>string</data_type>
                <required_on_create>false</required_on_create>
                <required_on_edit>false</required_on_edit>
            </arg>
            <arg name="split_savedsearches_conf">
                <title>Split savedsearches.conf files</title>
                <description>Unpack the savedsearces.conf file into a .git_savedsearches folder so that changes can be tracked more easily (doesnt affect regular Splunk operation).</description>
                <data_type>boolean</data_type>
                <required_on_create>false</required_on_create>
                <required_on_edit>false</required_on_edit>
            </arg>
            <arg name="include_btool_output">
                <title>Include Btool Output</title>
                <description>Btool output will be saved to files to track the layered Splunk configuration</description>
                <data_type>boolean</data_type>
                <required_on_create>false</required_on_create>
                <required_on_edit>false</required_on_edit>
            </arg>
            <arg name="btool_conf_files">
                <title>Btool Conf Files</title>
                <description>Comma separated list of .conf files which should be tracked for changes using Btool.</description>
                <data_type>string</data_type>
                <required_on_create>false</required_on_create>
                <required_on_edit>false</required_on_edit>
            </arg>
            <arg name="remote_push">
                <title>Remote Push</title>
                <description>Push changes to the remote repository on each run</description>
                <data_type>boolean</data_type>
                <required_on_create>false</required_on_create>
                <required_on_edit>false</required_on_edit>
            </arg>
        </args>
    </endpoint>
</scheme>"""


def get_input_config():
    """
    Reads and parses Splunk's XML configuration passed via sys.stdin.
    Returns a dictionary of configured stanzas and their parameters.
    """
    config = {}
    try:
        input_str = sys.stdin.read()
        if not input_str.strip():
            return config
            
        root = ET.fromstring(input_str)
        for stanza in root.findall(".//configuration/stanza"):
            stanza_name = stanza.attrib.get("name", "unknown")
            params = {}
            for param in stanza.findall("param"):
                param_name = param.attrib.get("name")
                param_val = param.text if param.text is not None else ""
                if param_name:
                    params[param_name] = param_val
            config[stanza_name] = params
    except Exception as e:
        print(f"ERROR Failed to parse Splunk stdin XML configuration: {str(e)}", file=sys.stderr)
    return config


def parse_bool(val):
    return str(val).strip().lower() in ("true", "1", "yes", "y", "t")


def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def split_savedsearches(event_data):

    # we dont unpack savedsearches in the "default" location as they dont resort themselves on change.
    patterns = [
        os.path.join("apps", "*", "local", "savedsearches.conf"),
        os.path.join("users", "*", "*", "local", "savedsearches.conf"),
    ]
    
    conf_files = []
    for pattern in patterns:
        conf_files.extend(glob.glob(pattern))
        
    for conf_file in set(conf_files):
        try:
            event_data.append("Splitting file: " + conf_file)            
            local_dir = os.path.dirname(conf_file)
            out_dir = os.path.join(local_dir, ".git_savedsearches")
            
            # may be a potentional issue here if modtime of directory changes unexpectedly
            if os.path.exists(out_dir) and os.path.getmtime(out_dir) >= os.path.getmtime(conf_file):
                continue
                
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            else:
                for f in os.listdir(out_dir):
                    os.unlink(os.path.join(out_dir, f))
                    
            stanzas = []
            current_name = None
            current_lines = []
            is_continuation = False
            
            with open(conf_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    clean_line = line.rstrip('\r\n')
                    
                    # Only check for a stanza header if the previous line was NOT escaped
                    if not is_continuation:
                        m = re.match(r'^\s*\[([^\]]+)\]', clean_line)
                        if m:
                            if current_lines:
                                stanzas.append((current_name or "default", "\n".join(current_lines)))
                            current_name = m.group(1)
                            current_lines = [clean_line]
                            is_continuation = clean_line.endswith('\\')
                            continue
                    
                    current_lines.append(clean_line)
                    is_continuation = clean_line.endswith('\\')
                    
            if current_lines:
                stanzas.append((current_name or "default", "\n".join(current_lines)))
                
            # Write individual stanza files
            for name, content in stanzas:
                if not content.strip():
                    continue
                    
                # 2. Filename Collisions and Limits: Calculate 6-char MD5 prefix
                md5_prefix = hashlib.md5(name.encode('utf-8', errors='ignore')).hexdigest()[:6]
                safe_name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:90]
                
                # Prepend MD5 and trim filename to max 120 characters (before .conf)
                file_base = f"{safe_name} [{md5_prefix}]"
                file_path = os.path.join(out_dir, file_base)
                
                # 6. Encoding Errors: Explicit UTF-8 for writing
                with open(file_path, "w", encoding="utf-8") as out_f:
                    out_f.write(content.strip() + "\n")
                    
        except Exception as e:
            event_data.append("Error splitting " + conf_file + ": " + str(e))


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


def output_event(params, data):
    stream = ET.Element("stream")
    event = ET.SubElement(stream, "event")
    ET.SubElement(event, "time").text = str(time.time())
    ET.SubElement(event, "index").text = params.get('index', "_internal")
    if params.get("host"):
        ET.SubElement(event, "host").text = params.get('host')
    ET.SubElement(event, "source").text = "gitforsplunk"
    ET.SubElement(event, "sourcetype").text = params.get('sourcetype', "sourcetype")
    ET.SubElement(event, "data").text = data
    xml_output = ET.tostring(stream, encoding="unicode")
    sys.stdout.write(xml_output + "\n")
    sys.stdout.flush()


def process_stanza(stanza_name, params):
    print(f"INFO Starting stanza={stanza_name} with input_params={params}", file=sys.stderr)
    event_data = []

    started = time.time()
    status = 2
    try:
        SPLUNK_HOME = os.environ['SPLUNK_HOME']
        event_data.append("GitForSplunk " + str(int(time.time())))
        
        event_data.append("SPLUNK_HOME=" + SPLUNK_HOME)

        working_directory = os.path.join(SPLUNK_HOME, params.get('working_directory'))
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
        my_env["GIT_DIR"] = os.path.join(working_directory, params.get('repository_directory'))
        event_data.append("GIT_DIR=" + my_env["GIT_DIR"])

        if parse_bool(params.get('include_btool_output')):
            btool_folder_name = "btool_output"
            btool_confs = [x.strip() for x in params.get('btool_conf_files').split(',')]
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

        if parse_bool(params.get('split_savedsearches_conf')):
            split_savedsearches(event_data)

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
                raise Exception(f"Unexpected return code of {ret_code}")
                
            git_size = calcDirSize(my_env["GIT_DIR"])
            m = re.search(r"\s(\d+ files? changed[^\r\n]+)", ret_output)
            if not m is None:
                ret_code, ret_output = gitcmd(["git", "commit", "--amend", "-m", "Auto: " + format((git_size / 1000000),'.0f') + " MB, " + str(m.group())], my_env, event_data)

            status = 1

            ret_code, ret_output = gitcmd(["git", "log", "--stat=150,120", "-1"], my_env, event_data)

            event_data.append("repo_size=" + str(git_size))

            if parse_bool(params.get('remote_push')):
                ret_code, ret_output = gitcmd(["git", "push"], my_env, event_data)
                if ret_code > 0:
                    raise Exception("Error occured - is authentication to remote site correct? and network path available?")

        status = 0

    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        event_data.append(template.format(type(ex).__name__, ex.args))

    runtime = round(time.time() - started)
    event_data.append("runtime=" + str(runtime))
    event_data.append("status=" + str(status))

    output_event(params, "\n".join(event_data))

    print(f"INFO Finished stanza={stanza_name} with status={status} runtime={runtime}s", file=sys.stderr)

    
def delete_legacy_files():
    # when splunk updates an app, it doeent clear the bin or appserver directories. however it does clear the default directory
    app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.exists(os.path.join(app_folder, "bin", "input_module_gitforsplunk.py")):
        os.remove(os.path.join(app_folder, "bin", "input_module_gitforsplunk.py"))    
    if os.path.exists(os.path.join(app_folder, "bin", "input_module_gitforsplunk.pyc")):
        os.remove(os.path.join(app_folder, "bin", "input_module_gitforsplunk.pyc"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_declare.py")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_declare.py"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_declare.pyc")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_declare.pyc"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_rh_gitforsplunk.py")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_rh_gitforsplunk.py"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_rh_gitforsplunk.pyc")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_rh_gitforsplunk.pyc"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_rh_settings.py")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_rh_settings.py"))    
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk_rh_settings.pyc")):
        os.remove(os.path.join(app_folder, "bin", "git_for_splunk_rh_settings.pyc"))
    if os.path.exists(os.path.join(app_folder, "bin", "git_for_splunk")):
        shutil.rmtree(os.path.join(app_folder, "bin", "git_for_splunk"))
    if os.path.exists(os.path.join(app_folder, "appserver")):
        shutil.rmtree(os.path.join(app_folder, "appserver"))


def main():
    """
    Main entry point. Handles Splunk CLI flags (--scheme) and standard scheduled execution via XML stdin.
    """
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--scheme", "-scheme"):
            print(SCHEME_XML)
            delete_legacy_files()
            sys.exit(0)
        elif arg in ("--validate-arguments", "-validate-arguments"):
            sys.exit(0)

    # Read XML from stdin and process configured stanzas
    inputs = get_input_config()
    if not inputs:
        print(f"ERROR No input configuration stanzas found in Splunk stdin stream", file=sys.stderr)
        sys.exit(0)

    for stanza_name, params in inputs.items():
        process_stanza(stanza_name, params)

    sys.exit(0)


if __name__ == "__main__":
    main()