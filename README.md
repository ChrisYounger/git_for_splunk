This Splunk app is quite basic, it could have just been a cronjob :) 
In a nutshell, it just runs the following commands:

* git add --all
* git commit -m "a reasonable, automatically generated message"
* git push (optionally)
* git log (so it can send an email)


As there are many unique and specific ways of creating git repositories, this app does not do that for you.  You will also need to configure .gitignore file correctly. See the documentation below for suggestions on .gitignore files.

Source code, issues or contributions: https://github.com/ChrisYounger/git_for_splunk


# Typical Installation Instructions

These instructions are for *nix, but the windows commands should be very similar. 

Start a shell as the user who runs Splunk. 

Make sure git is installed, and install it if not

* yum install git /or
* apt-get install git /or
* https://git-scm.com/downloads

Change to the directory from where you would like to track changes:

```
cd /opt/splunk/etc/
```

Initialise an empty repository:

```
git init 
```

Configure user settings, specific to the repository:

```
git config user.email splunk@mycompany.com
git config user.name Splunk
git config push.default simple
```

If desired, connect the repository to a remote repository  (adjust URL below as necessary).  Of course it would be silly to push to a public repository on GitHub or something so definitely don't do that. About at this point, you might need to setup SSH keys.

```
git remote add origin ssh://__SOME_GIT_URL__.git
```

Create a .gitignore file. See 'Customisations' section below for recommendations on what should be in .gitignore.

```
vi /opt/splunk/etc/.gitignore
```

Commit the .gitignore file and push to the remote repo. On this step make sure the that the push can happen without requiring credentials. You should be using ideally SSH keys but credential cache with a very long expiry should work OK too. 

```
git add .gitignore
git commit -m "initial check-in"
git push -u origin master
```

Now go into Splunk and configure the modular input. The easiest way is to navigate to Apps > 'Git for Splunk' > Inputs.





# Customisations

## Gitignore

Most Splunk environments have a lot of lookup tables that change regularly. Use the following gitignores to first disable tracking all lookup tables, but then selectively add the files you do care about.

```
**/lookups/*
!apps/search/lookups/my_important_lookup.csv
```

If you dont want to store sensitive information to be sent to an external repo, you probably want to ignore these sort of files (and others).

```
etc/auth/
etc/passwd
```

Other things you will probably want to ignore just becuase they are low value or change regularly.

```
*.pyc
*.log
users/**/history/*
login-info.cfg
local.meta
ui-prefs.conf
telemetry.conf
```

This helpful Splunk Answers post has a sample gitignore file: https://answers.splunk.com/answers/216267/what-do-you-put-in-your-gitignore-file-for-a-syste.html

If you aren't sure what to ignore, start by having no gitignore file and leave git_for_splunk run for a week. Then look at the supplied dashboard to see which files have been changing the most frequently. You can then add your own rules, delete the whole repo and start again. 

The following commands prevent a previously tracked file from being tracked anymore:

* cd /opt/splunk/etc/
* Update .gitignore to specify the file pattern to ignore.
* git add .gitignore
* git commit -m "Update gitignore file"
* git rm -r --cached .
* git add -A
* git commit -am 'Removing ignored files'
* git push



## Store the git repository outside of the Splunk folder

This can be a good idea to ensure that Splunk upgrades cannot delete the repository or if you want to store on a different drive.

Create a folder to store the local repository. It may require a lot of space depending on how many files are in the Splunk /etc/ folder

```
mkdir /opt/splunk_git_repo
```

Setup GIT environment variables so GIT knows where the repository is stored (*nix):

```
export GIT_DIR=/opt/splunk_git_repo/
export GIT_WORK_TREE=/opt/splunk/etc/
```

## Change the scheduled email alert to have a link to the changes   

This addon comes with a helpful email Alert action. It will email you to tell you what files have changed.

* Navigate to Apps > Git Version Control for Splunk > Alerts > Edit Alerts
* Configure a "To" email address
* If you are using an external repo such as BitBucket, GitLab, Gogs etc, you can edit the "Message" field and add a shortcut link to your external repo website. Be aware that the $body$ parameter will typically be the commit hash for the updated files so this should enable you to deep link into your repo's website.
* Enable the Alert


## Dealing with nested git repositories

Option 1) The best option is to alter your workflow in the nested repositories so that they store their .git folder out of the way. 

Option 2) This would be dubious, but you can use git hooks to hide the nested .git folders.

Create pre-commit file under .git/hooks/ of your root repo with contents:

```
#!/bin/sh
mv "vendor/modulename/.git" "vendor/modulename/.git2"
```

Create post-commit file under .git/hooks/ also with contents:

```
#!/bin/sh
mv "vendor/modulename/.git2" "vendor/modulename/.git"
```

Edit the .gitignore file to ignore .git2 folder. 

```
echo ".git2" >> .gitignore
```

You might also need to consider settings .gitignore to ignore nested .gitignore files  (**/.gitignore). Alternatively, you could alter the hooks to move/restore nested .gitignore files.

More reading: 

* https://stackoverflow.com/a/48649409/1653340
* https://stackoverflow.com/questions/23362967/how-to-tell-git-to-ignore-git-sub-modules
* https://stackoverflow.com/questions/14224966/merge-error-after-converting-git-submodule-to-subtree




## Third party software

The following third-party libraries are used by this app. Thank you!

* Font Awesome - CC BY 4.0 License - https://fontawesome.com/
* Splunk Add-on Builder - Splunk App End User License Agreement - https://splunkbase.splunk.com/app/2962/
