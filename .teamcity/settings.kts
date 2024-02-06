import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildFeatures.PullRequests
import jetbrains.buildServer.configs.kotlin.buildFeatures.commitStatusPublisher
import jetbrains.buildServer.configs.kotlin.buildFeatures.pullRequests
import jetbrains.buildServer.configs.kotlin.buildSteps.python
import jetbrains.buildServer.configs.kotlin.buildSteps.qodana
import jetbrains.buildServer.configs.kotlin.buildSteps.script
import jetbrains.buildServer.configs.kotlin.triggers.vcs

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

    buildType(QodanaQualityInspections)
    buildType(PytestPython39)
    buildType(PytestPython38)
    buildType(PytestPython310)
    buildType(PytestPython311)

    template(PytestRunner)
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

    params {
        password("system.qodana.developer-portal.edge-python-sdk.token", "credentialsJSON:d06aadf5-c6ee-4c2e-be77-c3395f5e5ad2", label = "Qodana Token", description = "The token for the build's Qodana project.", display = ParameterDisplay.HIDDEN, readOnly = true)
    }

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
            cloudToken = "credentialsJSON:7e58a4e2-e74e-4cc1-9668-de4ea5117706"
        }
    }

    triggers {
        vcs {
            branchFilter = "+:<default>"
        }
    }

    features {
        pullRequests {
            vcsRootExtId = "${DslContext.settingsRoot.id}"
            provider = github {
                authType = token {
                    token = "credentialsJSON:dfcd12f5-cec7-45dc-a612-43d2e7f70f5b"
                }
                filterTargetBranch = "+:refs/heads/main"
                filterAuthorRole = PullRequests.GitHubRoleFilter.EVERYBODY
            }
        }
        commitStatusPublisher {
            vcsRootExtId = "${DslContext.settingsRoot.id}"
            publisher = github {
                githubUrl = "https://api.github.com"
                authType = personalToken {
                    token = "credentialsJSON:dfcd12f5-cec7-45dc-a612-43d2e7f70f5b"
                }
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
        pullRequests {
            id = "BUILD_EXT_3"
            provider = github {
                authType = token {
                    token = "credentialsJSON:dfcd12f5-cec7-45dc-a612-43d2e7f70f5b"
                }
                filterTargetBranch = "+:refs/heads/main"
                filterAuthorRole = PullRequests.GitHubRoleFilter.EVERYBODY
            }
        }
        commitStatusPublisher {
            id = "BUILD_EXT_8"
            publisher = github {
                githubUrl = "https://api.github.com"
                authType = personalToken {
                    token = "credentialsJSON:dfcd12f5-cec7-45dc-a612-43d2e7f70f5b"
                }
            }
        }
    }
})
