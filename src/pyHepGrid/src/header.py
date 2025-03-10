import pyHepGrid.headers.template_header as template
import sys, os
from types import ModuleType
import getpass
import importlib
import pyHepGrid.extras.get_site_info as get_site_info
import pyHepGrid.src.logger as logmod
import socket
header_mappings = {"jmartinez":"pyHepGrid.headers.juan_header",
                   "dwalker":"pyHepGrid.headers.duncan_header",
                   "qpsv27":"pyHepGrid.headers.duncan_hamilton_header",
                   "jniehues":"pyHepGrid.headers.jan_header",
                   "jwhitehead":"pyHepGrid.headers.james_header",
                   "mheil":"HEJ.hej_header",
                   "andersen":"HEJ.hej_header"
                   }

if "phyip3" in socket.gethostname(): # Hack to get different headers for batch and grid w/ same username
    header_mappings["dwalker"]="headers.duncan_batch_header"

try:
    logger  = logmod.logger
except AttributeError as e:
    logger = logmod.setup_logger("INFO")
grid_username = getpass.getuser()
head = importlib.import_module(header_mappings[grid_username])

logger.info("Using header file {0}.py".format(head.__name__))

############ General header #################
# This should not be changed unless you really know what you are doing!
# Grid config

gsiftp   = "gsiftp://se01.dur.scotgrid.ac.uk/dpm/dur.scotgrid.ac.uk/home/pheno/generated/"
LFC_HOST = "lfc01.dur.scotgrid.ac.uk"
LFC_CATALOG_TYPE = "lfc"
runfile = "nnlorun.py"
runmode = "NNLOJET"
sandbox_dir = "test_sandbox"
arc_direct = True
split_dur_ce = True
slurm_kill_exe = "{0}/kill_server.py".format(os.path.dirname(os.path.realpath(__file__)))

# Database config
arctable   = "arcjobs"
arcprodtable   = "arcjobs"
diractable = "diracjobs"
slurmtable = "slurmjobs"
slurmprodtable = "slurmjobs"
dbfields   = ['jobid', 'date', 'runcard', 'runfolder', 'pathfolder', 'status', 'jobtype', 'iseed', 'sub_status', "queue", "no_runs"]

# DW This should be a hard link so socketed runs can be sent from other folders/locations
socket_exe = "{0}/socket_server.py".format(os.path.dirname(os.path.realpath(__file__))) # Eventually will need to point towards where the sockets are
sockets_active = 1 # 1 socket == no sockets

############ COPY NAMESPACE FROM MY_HEADER #############
# Only slightly abusive...
this_file = sys.modules[__name__]

# Check that the all of the attributes in template are present...
template_namespace = [i for i in dir(template) if not i.startswith("__")]
# remove functions from template namespace
template_attributes = [i for i in template_namespace if not
                       callable(getattr(template, i))]
# remove modules from template namespace
template_attributes = [i for i in template_namespace if not
                       isinstance(getattr(template, i),ModuleType)]

for temp_attr in template_attributes:
    logger.debug("{0:20}: {1}".format(temp_attr,getattr(head,temp_attr)))

# Set attributes inside header
for i in dir(head):
    if not i.startswith("__"):
        attr = getattr(head,i)
        setattr(this_file,i,attr)
        # Give warnings if you've added any new attributes and not put them in the template.
        if i not in template_attributes and not isinstance(attr,ModuleType)\
                and not callable(attr) and i not in ["arcprodtable","slurmprodtable"]:
            logger.warning("attribute {0} not present in {1}".format(i, template.__name__))
            logger.info("Please add it in before committing so you don't break compatibility(!)")

# Raise errors if you try to run without parameters specified in the template
for i in template_attributes:
    try:
        assert(hasattr(this_file, i))
    except AssertionError as e:
        logger.error("Missing attribute {0} inside {1}.py that is present in {2}.py.".format(
                i, head.__name__, template.__name__))
        logger.info("Check that {0}.py file is up to date as functionality may be broken otherwise.".format(head.__name__))
        sys.exit(1)

#### RUNCARD OVERRIDES ####
from pyHepGrid.src.argument_parser import runcard as runcard_file
if runcard_file:
    runcard = importlib.import_module(runcard_file.replace(".py","").replace("/","."))
    # todo: some safety checks
    for attr_name in dir(runcard):
        if not attr_name.startswith("__") and not \
                isinstance(getattr(runcard, attr_name), ModuleType):
            if not hasattr(this_file, attr_name) and attr_name != "dictCard" :
                logger.warning("{0} defined in {1}.py but not {2}.py.".format(attr_name, runcard.__name__, template.__name__))
                logger.info("Be very careful if you're trying to override attributes that don't exist elsewhere.")
                logger.info("Or even if they do.")

            attr_value = getattr(runcard, attr_name)
            if attr_name != "dictCard":
                logger.value(attr_name, attr_value, runcard.__name__)
            setattr(this_file, attr_name, attr_value)
try:
    from pyHepGrid.src.argument_parser import override_ce_base as use_best_ce
    if use_best_ce:
        setattr(this_file, "ce_base", get_site_info.get_most_free_cores())
        logger.value("ce_base", ce_base, get_site_info.get_most_free_cores())
except ImportError as e:
    pass

#### CMD LINE ARG OVERRIDES ####

try:
    from pyHepGrid.src.argument_parser import additional_arguments
    for attr_name in additional_arguments:
        new = False
        if not hasattr(this_file, attr_name) and attr_name is not "dictCard":
            logger.warning("{0} defined in command line args but not in {1}.py.".format(attr_name, template.__name__))
            logger.info("Be very careful if you're trying to override attributes that don't exist elsewhere.")
            logger.info("Or even if they do.")
            new = True

        attr_value = additional_arguments[attr_name]
        if not new: # Not a new argument only defined at cmd line args
            try:
                if attr_name == "dictCard":
                    import ast
                    attr_value = ast.literal_eval(attr_value)
                else:
                    attrtype = type(getattr(this_file,attr_name))
                    if attrtype is type(dict()):
                        import ast
                        attr_value = ast.literal_eval(attr_value)
                    elif attrtype is not type(None):
                        attr_value = attrtype(attr_value) # Casts the value to the type of the value found already in the header. If not found or the type is None, defaults to a string.
            except AttributeError as e:
                logger.warning("{0} default type not found.".format(attr_name))
                logger.info("Will be passed through as a string.")
            except ValueError as e:
                logger.error("Additional argument {0} with value {1} cannot be coerced into expected type {2}.".format(attr_name,attr_value,attrtype.__name__))
                sys.exit(-1)
        logger.value(attr_name, attr_value,"command line args")
        setattr(this_file, attr_name, attr_value)
except ImportError as e:
    pass

### Moved to the bottom to allow runcard to override jobName/arcbase

if arcbase is None and os.path.basename(os.path.realpath(sys.argv[0]))=="main.py":
        logger.critical("arcbase (location of arc submission database) set to None. Please check your header/runcard.")

#
# Templates
#

# # If a job is expected to run for long, use the following property (in minutes)
# "(wallTime  =    \"3 days\")"
# it is also possible to specifiy the maximum cpu time instead (or 'as well')
# "(cpuTime = \"3 days\")"
# if nothing is used, the end system will decide what the maximum is
#

ARCSCRIPTDEFAULT = ["&",
        "(executable   = \"{0}\")".format(runfile),
        "(outputFiles  = (\"outfile.out\" \"\") )",
        "(stdout       = \"stdout\")",
        "(stderr       = \"stderr\")",
        "(gmlog        = \"testjob.log\")",
        "(memory       = \"100\")",
        ]

ARCSCRIPTDEFAULTPRODUCTION = ["&",
        "(executable   = \"{0}\")".format(runfile),
        "(outputFiles  = (\"outfile.out\" \"\") )",
        "(stdout       = \"stdout\")",
        "(stderr       = \"stderr\")",
        "(gmlog        = \"testjob.log\")",
        "(memory       = \"100\")",
        ]

DIRACSCRIPTDEFAULT = [
    "JobName    = \"{0}\";".format(jobName),
    "Executable = \"{0}\";".format(runfile),
    "StdOutput  = \"StdOut\";",
    "StdError   = \"StdErr\";",
    "InputSandbox  = {{\"{0}\"}};".format(runfile),
    "OutputSandbox = {\"StdOut\",\"StdErr\"};",
    "Platform = \"{0}\";".format(dirac_platform)
        ]

# If Dirac banned sites are specified, include them in JDL
if DIRAC_BANNED_SITES is not None:
    DIRACSCRIPTDEFAULT.append("BannedSites = {{\"{0}\"}};".format("\",\"".join(DIRAC_BANNED_SITES)))

_slurmfilename = os.path.join(os.path.dirname(os.path.realpath(__file__)),"slurm_template.sh")
with open(_slurmfilename) as template_file:
    SLURMSCRIPTDEFAULT = template_file.read()

_slurmfilename_production = os.path.join(os.path.dirname(os.path.realpath(__file__)),"slurm_template_production.sh")
with open(_slurmfilename_production) as template_file:
    SLURMSCRIPTDEFAULT_PRODUCTION = template_file.read()
