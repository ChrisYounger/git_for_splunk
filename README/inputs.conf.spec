[gitforsplunk://<name>]
working_directory = This is the path which will be tracked for changes. Relative to SPLUNK_HOME or an absolute path
repository_directory = The path where the git repository will be stored. Relative to the working directory or an absolute path.
include_btool_output = Btool output will be saved to files to track the layered Splunk configuration
btool_conf_files = Comma separated list of .conf files which should be tracked for changes using Btool.
remote_push = Push changes to the remote repository on each run
