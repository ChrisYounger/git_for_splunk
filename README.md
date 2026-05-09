Simple version control of Splunk. Zero-effort versioning of your dashboards, .conf changes, saved searches etc.

This Splunk app will use git to track file changes on a schedule. It can then optionally push the changes to an external repository. This app is useful if you want to know what and when files change in your environment. Unfortunately this app won't tell you "who" made a change - but typically you can get a pretty good idea with the help of Splunk audit logs etc.

Before each run, this app can run a btool dump of various conf files. This is important because individual savedsearches files reorder as they are updated through the UI, which makes diffs ugly. The btool dump is always in a consistent order.



Please see the documentation at Splunkbase https://splunkbase.splunk.com/app/4182 >> Details tab.



Source code, issues or contributions: https://github.com/ChrisYounger/git_for_splunk

