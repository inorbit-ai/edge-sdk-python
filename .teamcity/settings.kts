import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildFeatures.PullRequests
import jetbrains.buildServer.configs.kotlin.buildFeatures.commitStatusPublisher
import jetbrains.buildServer.configs.kotlin.buildFeatures.pullRequests
import jetbrains.buildServer.configs.kotlin.buildSteps.python
import jetbrains.buildServer.configs.kotlin.buildSteps.qodana
import jetbrains.buildServer.configs.kotlin.buildSteps.script
import jetbrains.buildServer.configs.kotlin.triggers.vcs
import jetbrains.buildServer.configs.kotlin.vcs.GitVcsRoot

/*
The settings script is an entry point for defining a TeamCity
project hierarchy. The script should contain a single call to the
project() function with a Project instance or an init function as
an argument.

VcsRoots, BuildTypes, Templates, and subprojects can be
registered inside the project using the vcsRoot(), buildType(),
template(), and subProject() methods respectively.

To debug settings scripts in command-line, run the

    mvnDebug org.jetbrains.teamcity:teamcity-configs-maven-plugin:generate

command and attach your debugger to the port 8000.

To debug in IntelliJ Idea, open the 'Maven Projects' tool window (View
-> Tool Windows -> Maven Projects), find the generate task node
(Plugins -> teamcity-configs -> teamcity-configs:generate), the
'Debug' option is available in the context menu for the task.
*/

version = "2023.11"

project {
    description = "The InOrbit Edge SDK allows Python programs to communicate with InOrbit platform on behalf of robots."

    vcsRoot(HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain)

    buildType(QodanaQualityInspections)
    buildType(PytestPython39)
    buildType(PytestPython38)
    buildType(PytestPython310)
    buildType(PytestPython311)

    template(PytestRunner)

    params {
        password("system.qodana.open-source.edge-sdk-python.token", "credentialsJSON:4d17e6f7-909d-4025-8236-194c7941c16c", label = "Qodana Token", description = "Qodana Open-source edge-sdk-python Token", display = ParameterDisplay.HIDDEN, readOnly = true)
    }
    buildTypesOrder = arrayListOf(PytestPython38, PytestPython39, PytestPython310, PytestPython311)
}

object PytestPython310 : BuildType({
    templates(PytestRunner)
    name = "Pytest Python 3.10"
    description = "Pytest runner for Python 3.10 tests."

    params {
        text("python.version", "3.10", label = "Python Version", description = "The version of Python to run this build with.",
              regex = """^(\d+\.)?(\d+\.)?(\*|\d+)${'$'}""", validationMessage = "Please enter a valid version number.")
    }
})

object PytestPython311 : BuildType({
    templates(PytestRunner)
    name = "Pytest Python 3.11"
    description = "Pytest runner for Python 3.11 tests."

    params {
        text("python.version", "3.11", label = "Python Version", description = "The version of Python to run this build with.",
              regex = """^(\d+\.)?(\d+\.)?(\*|\d+)${'$'}""", validationMessage = "Please enter a valid version number.")
    }
    
    disableSettings("TRIGGER_4")
})

object PytestPython38 : BuildType({
    templates(PytestRunner)
    name = "Pytest Python 3.8"
    description = "Pytest runner for Python 3.8 tests."

    params {
        text("python.version", "3.8", label = "Python Version", description = "The version of Python to run this build with.",
              regex = """^(\d+\.)?(\d+\.)?(\*|\d+)${'$'}""", validationMessage = "Please enter a valid version number.")
    }
})

object PytestPython39 : BuildType({
    templates(PytestRunner)
    name = "Pytest Python 3.9"
    description = "Pytest runner for Python 3.9 tests."

    params {
        text("python.version", "3.9", label = "Python Version", description = "The version of Python to run this build with.",
              regex = """^(\d+\.)?(\d+\.)?(\*|\d+)${'$'}""", validationMessage = "Please enter a valid version number.")
    }
})

object QodanaQualityInspections : BuildType({
    name = "Qodana Quality Inspections"
    description = "Qodana based code quality inpsections."

    vcs {
        root(DslContext.settingsRoot)
    }

    steps {
        qodana {
            name = "Qodana"
            id = "Qodana"
            linter = python {
            }
            additionalQodanaArguments = "--baseline qodana.sarif.json"
            cloudToken = "credentialsJSON:809f8c61-4df0-4d12-a554-0f2c13a4b8f2"
        }
    }

    features {
        commitStatusPublisher {
            vcsRootExtId = "${HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain.id}"
            publisher = github {
                githubUrl = "https://api.github.com"
                authType = personalToken {
                    token = "credentialsJSON:4cdab6f6-2273-4bad-a1b5-ae7442084c8b"
                }
            }
        }
        pullRequests {
            vcsRootExtId = "${HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain.id}"
            provider = github {
                authType = token {
                    token = "credentialsJSON:4cdab6f6-2273-4bad-a1b5-ae7442084c8b"
                }
                filterTargetBranch = "+:refs/heads/main"
                filterAuthorRole = PullRequests.GitHubRoleFilter.EVERYBODY
            }
        }
    }
})

object PytestRunner : Template({
    name = "Pytest Runner"
    description = "Generic runner for Pytest."

    allowExternalStatus = true

    params {
        text("python.version", "", label = "Python Version", description = "The version of Python to run this build with.",
              regex = """^(\d+\.)?(\d+\.)?(\*|\d+)${'$'}""", validationMessage = "Please enter a valid version number.")
    }

    vcs {
        root(DslContext.settingsRoot)

        cleanCheckout = true
        branchFilter = ""
    }

    steps {
        script {
            name = "Update and Setup"
            id = "Update_and_Setup"
            scriptContent = """
                sudo add-apt-repository ppa:deadsnakes/ppa
                sudo apt-get update
                
                sudo apt-get install -y python%python.version% python%python.version%-distutils
                
                wget -P /tmp/ https://bootstrap.pypa.io/get-pip.py
                sudo python%python.version% /tmp/get-pip.py
            """.trimIndent()
        }
        python {
            name = "Update pip"
            id = "Update_pip"
            pythonVersion = customPython {
                executable = "/usr/bin/python%python.version%"
            }
            command = custom {
                arguments = "-m pip install --upgrade pip"
            }
        }
        python {
            name = "Install pip Dependencies"
            id = "Install_pip_Dependencies"
            pythonVersion = customPython {
                executable = "/usr/bin/python%python.version%"
            }
            command = custom {
                arguments = "-m pip install .[test]"
            }
        }
        python {
            name = "Pytest Runner"
            id = "Pytest_Runner"
            pythonVersion = customPython {
                executable = "/usr/bin/python%python.version%"
            }
            command = pytest {
                isCoverageEnabled = true
                coverageArgs = "--omit=*lib* --source=inorbit_edge/"
            }
        }
    }

    triggers {
        vcs {
            id = "TRIGGER_6"
            triggerRules = "+:*"
        }
    }

    features {
        commitStatusPublisher {
            id = "BUILD_EXT_6"
            vcsRootExtId = "${HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain.id}"
            publisher = github {
                githubUrl = "https://api.github.com"
                authType = personalToken {
                    token = "credentialsJSON:4cdab6f6-2273-4bad-a1b5-ae7442084c8b"
                }
            }
        }
        pullRequests {
            id = "BUILD_EXT_7"
            vcsRootExtId = "${HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain.id}"
            provider = github {
                authType = token {
                    token = "credentialsJSON:4cdab6f6-2273-4bad-a1b5-ae7442084c8b"
                }
                filterAuthorRole = PullRequests.GitHubRoleFilter.EVERYBODY
            }
        }
    }
})

object HttpsGithubComInorbitAiEdgeSdkPythonRefsHeadsMain : GitVcsRoot({
    name = "https://github.com/inorbit-ai/edge-sdk-python#refs/heads/main"
    url = "https://github.com/inorbit-ai/edge-sdk-python"
    branch = "refs/heads/main"
    authMethod = password {
        userName = "%system.github.username%"
        password = "credentialsJSON:4cdab6f6-2273-4bad-a1b5-ae7442084c8b"
    }
})
