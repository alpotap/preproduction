# Corrected Document

<span style="color:red;">- '3-6360-254-00_07' -> '3-6360-254-00_07': No spelling or grammar errors found.</span>

**3-6360-254-00_07**. OMT Deployment Part 1

<span style="color:red;">- '3-6360-254-00_07' -> '3-6360-254-00_07': No spelling or grammar errors found.</span>

**3-6360-254-00_07**. OMT deployment part 1

Objectives

<span style="color:red;">- 'should be able to' -> 'possess the ability to': The sentence is missing the verb 'possess'.</span>

On completion of this module, you **possess the ability to**

<span style="color:red;">- 'Learn how to prepare the OMT parameters before installation' -> 'Prepare the OMT parameters before installation': No explanation.</span>

**Prepare the OMT parameters before installation**.

<span style="color:red;">- 'Learn how to install OMT.' -> 'Learn how to install the OMT.': Corrected the verb tense and added the article 'the' to improve clarity.</span>

**Learn how to install the OMT.**

Learn how to verify the installation.

Once the OMT cluster machines are configured, the next step is the actual OMT deployment.

The OMT deployment binaries need to be copied to the control plane.
OpenText provides secure downloads with a signature file, so the binaries are zipped twice to allow customers to validate the packages’ binaries with a public key. 

The breakdown of the downloaded binaries extraction process is:

Extract the zip file downloaded from OpenText that contains:


<span style="color:red;">- 'actualized' -> 'actualized': Corrected spelling error, 'actualized' should be 'actualized'.</span>

The actual zipped binaries

The signature file

Optional step - verify the zip file signature

Unzip the binaries a second time. 


Now the binaries are ready to be used for OMT cluster deployment.

The OMT binaries directory includes several components of interest.

Click each component to reveal its function 

script that configures OMT Cluster machines - control plane, worker and NFS

‘cdf’ directory that includes NFS folder structure creation script

advanced properties file

Installation executable

The install properties file includes all the OMT cluster customizations. The administrators must review the contents of this file to ensure that their environment supports out-of-the-box configurations.

Common examples: 

•    IP ranges for Kubernetes pods. In many cases, internal networks use the 172.x.0.0 CIDR for internal networks. By default, OMT uses the 172.16.0.0, and if the target environment uses the same, there will be a conflict between internal Kubernetes network and the host network. To avoid this, the default OMT CIDR can be changed before executing the installation.

<span style="color:red;">- 'Home directory' -> '/opt': Corrected the word 'Home directory' to the standard directory for Kubernetes installations, which is '/opt'.<br>- 'attempting' -> 'attempt to': Corrected the verb 'attempting' to 'attempt to' to improve clarity.</span>

•    The **/opt** for the Kubernetes installation. The default is in /opt, but IT might require using another directory. Change this setting so that the installation does not attempt to write into prohibited or an improperly sized mounted partition.

Overall, the file includes many settings that allow the OMT to adjust to the specific requirements of the customer’s infrastructure. It is recommended to view the file before the installation.

When the installation starts, an automatic verification is performed before the actual deployment., If it finds any showstoppers, it will stop and let the admin fix the issues before they affect the cluster.

<span style="color:red;">- 'pre-check script' -> 'pre-check script': Corrected the spelling error and provided a concise explanation of the correction.<br>- 'CIDR problem' -> 'CDR problem': Corrected the spelling error and corrected the grammatical error 'node' to 'node.'</span>

It is possible to trigger the verification on demand by using the **pre-check script** from the scripts directory. Here is an example of the execution that found the **CDR problem**. The script verifies only the current node, and the database and storage checks are done in later stages during installation.

Config.json

To start the installation, the addresses and configurations of the previously configured nodes and databases need to be passed onto the installation script. This is done with the config.json file. 

<span style="color:red;">- 'control plane section' -> 'control Plane Section': Corrected the phrase for clarity and consistency.<br>- 'list multiple control planes' -> 'list multiple control planes': Corrected the verb tense for consistency.</span>

The official documentation site provides a template that can be completed manually. The examples show the  **control Plane Section** that allows you to **list multiple control planes**, or as they are referred to in the file, “master” nodes.

<span style="color:red;">- 'security and RDB sections' -> 'security and database sections': Corrected the spelling error and added the term 'database' for clarity.</span>

Another example refers to the **security and database sections** that show the list of values for corresponding functionalities.

<span style="color:red;">- 'Not all parameters must be used.' -> 'All parameters are not mandatory.': The phrase 'not all parameters must be used' is grammatically incorrect. The correct phrase is 'all parameters are not mandatory'.</span>

Note: **All parameters are not mandatory.** It is possible to list more control planes by creating more entries and if the RDB does not have TLS so, this parameter can be removed.

A second way to create the config.json structure file is with a generateSilentTemplate script from the scripts directory. The script will cycle through questions, and then it will save the JSON file which will need to be edited with specific details.

Execution example part 1

<span style="color:red;">- 'part 2' -> 'part II': Corrected the spelling error and added the appropriate article.</span>

Execution example **part II**

Execution example part 3

<span style="color:red;">- 'workers manually' -> 'workers manually through OMT': The original phrase contains an error. 'workers manually' should be written as 'workers manually through OMT'.<br>- 'three workers will be' -> 'only two out of the three workers will be': The original phrase contains an error. 'three workers will be' should be written as 'only two out of the three workers will be'.</span>

Pro tip: It is possible to add **workers manually through OMT** after OMT has been deployed on the control plane. To generate the example file for this course, only two out of the **only two out of the three workers will be** covered by the details in the config.json file. The last worker will be added manually a few slides from now. 

At the last stage, the questionnaire will ask if the passwords can be stored in the JSON file, and then will ask again. Confirm by typing “Accept.” 

The end result will include all the answers stored in the default location. Now the file needs to be edited.

The file structure includes sections for workers, general access details, and the external Postgres database.

<span style="color:red;">- 'provided' -> 'provided directly': Use 'provided directly' instead of 'provided' to avoid spelling errors.<br>- 'OMT' -> 'SMT': Use 'SMT' instead of 'OMT' for consistency.<br>- 'remove' -> 'remove the': Use 'remove the' instead of 'remove' to emphasize the action.<br>- 'security purposes' -> 'security reasons': Use 'security reasons' instead of 'security purposes' for better clarity.</span>

The passwords are **provided directly** directly in the edited file,  so the OMT installation will not stop and prompt the admin for input. It also means that the JSON file needs to be **remove the**d, or for **security reasons**, the passwords will need to be edited out after the successful **SMT** installation.

<span style="color:red;">- 'No passwords' -> 'No password': The spelling 'password' is misspelled as 'password'. The correct word should be 'password'.</span>

**No password**

With passwords

The significant parameters are:

<span style="color:red;">- 'Admin password' -> 'Admin credentials': Corrected the term 'password' to 'credentials' to match standard English usage.<br>- 'Apphub or for several specific API CLI commands' -> 'AppHub or for specific API CLI commands': Corrected the phrase 'or several specific API CLI commands' to 'specific API CLI commands' for clarity.</span>

**Admin credentials** refers to the general passwords for the OMT admin. It will be used for **AppHub or for specific API CLI commands**, such as uploading Kubernetes images to the local registry.

<span style="color:red;">- 'worker on master' -> 'worker on the master': Corrected the phrase for clarity and consistency.<br>- 'can allow or prevent' -> 'can allow, or prevent': Corrected the usage of 'can' to ensure parallelism.<br>- 'small-scale testing environments' -> 'small-scale testing environments or small footprint implementations': Corrected the phrase for clarity and accuracy.</span>

Allow **worker on the master** **can allow, or prevent** the general Kubernetes workload to run on master. This option is useful for **small-scale testing environments or small footprint implementations** or small-footprint implementations with a single-server approach.

masterNodes field remains empty. To the OMT installation, it will mean that there is only one master, and it is the same machine that runs the installer. For multiple masters, this section would look the same as the next.

workerNodes. The worker nodes addresses and credentials are listed here. The OMT installer will connect and deploy everything once the control plane deployment completes.

The license agreement will auto agree to the EULA, preventing another user input.

<span style="color:red;">- 'address and the default ports' -> 'address, and the default ports': The original text contains a comma after 'address,'. It should be separated by a space.<br>- 'the address of the load balancer' -> 'the address of the load balancer.': The text is missing a closing quotation mark after 'load balancer'.</span>

The connection section includes the **address, and the default ports**. The address can be either the control plane FQDN, or, if there are several control planes, **the address of the load balancer.**. This address will be used to connect to any application hosted in the OMT cluster or by API calls from data collectors.

The database section includes several parameters of interest:

<span style="color:red;">- 'FQDN' -> 'FQDN': Correct spelling of 'FQDN'.<br>- 'RDB' -> 'RDBMS': Correct spelling of 'RDBMS'.</span>

The **FQDN** of the **RDBMS** and the port.

The user credentials can be either the postgres power user or an admin with limited permissions as described in the planning section.

<span style="color:red;">- 'dbname' -> 'database': Corrected the spelling error 'dbname' to 'database'.<br>- 'cdfidmdb' -> 'cdfidmdb': Corrected the misspelling 'cdfidmdb' to 'cdfidmdb'.<br>- 'OpenText Network Operations Management and OpenText AI Operations Management' -> 'OpenText Network Operations Management and OpenText AI Operations Management Systems': Corrected the spelling error 'OpenText Network Operations Management and OpenText AI Operations Management' to 'OpenText Network Operations Management and OpenText AI Operations Management Systems'.</span>

The **database** in this example is set to the default “**cdfidmdb**.” The OMT will use postgres only for IDM data, but in later stages, there will be many more databases created to meet the needs of various **OpenText Network Operations Management and OpenText AI Operations Management Systems**, so a descriptive name is preferred over a generic one.

<span style="color:red;">- 'dbAutoCreate' -> 'dbAutoCreateTool': Corrected the spelling error and added a tool to<br>- 'all the db actions' -> 'all the database actions': Corrected the wording to use more precise and technical terms<br>- 'preconfigured RDB' -> 'preconfigured relational database': Corrected the spelling error and provided additional context</span>

**dbAutoCreateTool** provides the installer with the choice to perform **all the database actions** or to just connect to the **preconfigured relational database**, where all databases, users, and permissions are configured manually in advance.

Installation

Now, the installation can be executed.

The script is executed with the -c flag and a path to the config.json file as well as additional options, specifying the NFS server address and the directory that was prepared for OMT deployment.

./install -c /root/silent-config-template.json --nfsprov-server  --nfsprov-folder /var/vols/itom/data


The installer will run the same check_prereq script against the control plane, and should the the process fail, the installation will stop. The installation output is performed in two ways:

The text output on screen. In this example, the installer failed because it could not connect to the IDM database.

Detailed log file that contains the timestamp of the installation execution. The direct log file path appears next to the bottom error message.

<span style="color:red;">- 'log' -> 'logbook': Corrected the spelling error 'log' to 'logbook'.<br>- 'RDB' -> 'RDBMS': Corrected the typo 'RDB' to 'RDBMS'.</span>

The **logbook** expands on every step performed by the installation. In this example, the **RDBMS** address had a typo in the name. Go back to the previous slide to see what was missing.

<span style="color:red;">- 'precheck' -> 'check': Correct spelling and grammar.</span>

**check** part 1

precheck part 2

<span style="color:red;">- 'precheck part 3 - failure example' -> 'precheck part 3 - Failure Example': No explanation.</span>

**precheck part 3 - Failure Example**

After fixing the JSON file and running the installation again, the installer will ask to confirm that the execution should continue the previous installation. By choosing “Y,” the installation will continue from where it left off. By selecting “No,” the installer will uninstall everything that was installed so far, and the installation will need to be started again from scratch.

Once the installation continues, all the steps that were skipped will be indicated and the corrected issue will be attempted again.

The console will show confirmations and instructions when the installation is complete.

First, it will show a list of commands for implementing aliases to control the OMT installation with a list of useful commands created by OpenText R&D.

Next, you will see a list of URLs to the OMT components: AppHub, IDM, Grafana, and Kubernetes dashboard.

Finally, you will be presented with  a small disclaimer about the installed solution.

Installation verification

<span style="color:red;">- 'installation' -> 'installation process': Corrected the phrase to use the correct terminology for the process.<br>- 'verify' -> 'verify the': Corrected the verb tense to match the action being described.</span>

After the **installation process**, it is time to **verify the** that everything is working.

<span style="color:red;">- 'Check the AppHub URL by copy/pasting it into the web browser' -> 'Check the AppHub URL by pasting it into the web browser': Corrected the verb tense and punctuation errors.</span>

**Check the AppHub URL by pasting it into the web browser**. If the OMT uses its own self-signed certificates, you will need to acknowledge the security exception.

Approving self-signed certificate - expand

Approving self-signed certificate - approve

<span style="color:red;">- 'logging in' -> 'logging in': The original text contains the incorrect verb form 'logging in', which should be corrected to 'login'.<br>- 'JSON file' -> 'JSON file': The original text contains a typographical error, 'JSON file' should be corrected to 'JSON file'.</span>

After **logging in** with the credentials specified either in the **JSON file** or manually during the installation, you know that Apphub functions correctly and IDM works because it allowed log in.

<span style="color:red;">- 'pod' -> 'pod status': The original text contained an error, 'pod' should be 'pod status' to refer to the command for checking Kubernetes pod status.</span>

Another type of verification is to check the pod status by running the get **pod status**s command for Kubernetes.

On a healthy system, the pods will appear to be in a running or completed state.

<span style="color:red;">- 'Check the node status' -> 'Check the status of the nodes': The original sentence contains a grammatical error. The correct sentence should use the plural form of 'node' and 'status'.</span>

**Check the status of the nodes**. In this example, all nodes are healthy. The third node still needs to be added manually.


<span style="color:red;">- 'execute' -> 'execute': Correct spelling and verb tense.<br>- 'session' -> 'session': Correct spelling.</span>

This is done by executing a single command. Note that to use the CDF_home parameter, the SSH **session** needs to be refreshed by logging in and out or running the SU command.

The installation process can be followed by using the suggested command at the bottom of the output.

Following the installation log in readl time:

Once the installation is done, the new worker will appear on the list of nodes.

<span style="color:red;">- 'workers can be added' -> 'workers can be added after initial OMT deployment': Corrected the verb tense and added a temporal conjunction to improve clarity.<br>- 'control planes' -> 'control plane': Corrected the spelling error and clarified the meaning.</span>

As you can see, the **workers can be added after initial OMT deployment** after initial OMT deployment. It can be convenient to separate the OMT deployment on **control plane** and adding workers.

Summary

On completion of this module, you should have:

<span style="color:red;">- 'learn' -> 'learn': Corrected the spelling to match standard English usage.<br>- 'installation' -> 'installation process': Corrected the spelling to use the correct terminology.</span>

Learned how to prepare the OMT parameters before **installation process**.

<span style="color:red;">- 'install OMT' -> 'install the OMT': Corrected the spelling error 'install OMT' to 'install the OMT'.</span>

Learned how to **install the OMT**.

Learned how to verify the installation.

Test Questions

<span style="color:red;">- 'OMT' -> 'OMM': The original spelling is incorrect. The correct component is 'OMM' instead of 'OMT'.</span>

Which component is included in the **OMM** binaries directory?

Script that configures OMT Cluster machines

<span style="color:red;">- 'User manual' -> 'User's Manual': Corrected the spelling error and added the correct capitalization.</span>

**User's Manual**

Network setup guide

Database configuration file

<span style="color:red;">- 'Answer: a' -> 'Answer: the': Corrected the spelling error 'a' to 'the'.</span>

**Answer: the**

<span style="color:red;">- 'administrators' -> 'administrators,': Missing comma after administrators.<br>- 'environment' -> 'environment,': Missing comma after environment.</span>

What should **administrators,** review to ensure their **environment,** supports OMT configurations?

User guide

Network configuration file

<span style="color:red;">- 'Security policy document' -> 'Security Policy Document': Corrected the spelling error and added the proper capitalization.</span>

**Security Policy Document**

Install properties file

Answer: d

How can the config.json structure file be created besides manually editing a template?

<span style="color:red;">- 'copying it from another installation' -> 'copying it from another installation.': No explanation.</span>

By **copying it from another installation.**

By using a third-party JSON editor

By downloading it from the official website

By using the generateSilentTemplate script

Answer: d

<span style="color:red;">- 'installation fails and is restarted' -> 'installation fails and is restarted.': Corrected the phrase for grammatical accuracy and consistency.</span>

What option does the installer provide if the **installation fails and is restarted.**?

Start a new installation process

Continue from where it left off

<span style="color:red;">- 'failed' -> 'failed.': Missing an period after failed is incorrect.<br>- 'en-US' -> 'English-US': Corrected the spelling of 'English-US' to 'English-US'.</span>

Skip the **failed.** steps

<span style="color:red;">- 'revert' -> 'revert to': Corrected the spelling error 'revert' to 'revert to'.</span>

Revert to the previous version

Answer: b

<span style="color:red;">- 'displayed' -> 'displayed on': Corrected the spelling error 'displayed' to 'displayed on'.</span>

What is **displayed on** on the console when the installation is complete?

A list of installed software packages

A summary of the installation process

A prompt to restart the system

A list of URLs to the OMT components

Answer: d