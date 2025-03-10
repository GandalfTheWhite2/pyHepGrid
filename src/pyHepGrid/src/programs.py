import os
import sys
from pyHepGrid.src.header import logger
import pyHepGrid.src.utilities as util
import pyHepGrid.src.header as header
from pyHepGrid.src.runcard_parsing import PROGRAMruncard, warmup_extensions
from pyHepGrid.src.program_interface import ProgramInterface


class NNLOJET(ProgramInterface):
    # IMPORTANT: NAMING FUNCTIONS SHOULD BE THE SAME IN RUNFILE
    def warmup_name(self, runcard, rname):
        out = "output{0}-warm-{1}.tar.gz".format(runcard, rname)
        return out

    def output_name(self, runcard, rname, seed):
        out = "output{0}-{1}-{2}.tar.gz".format(runcard, rname, seed)
        return out

    # Checks for the runcard
    def _check_production(self, runcard):
        logger.debug("Checking production in runcard {0}".format(runcard.name))
        if runcard.is_warmup():
            self._press_yes_to_continue("Warmup is active in runcard")
        if not runcard.is_production():
            self._press_yes_to_continue("Production is not active in runcard")

    def _check_warmup(self, runcard, continue_warmup=False):
        logger.debug("Checking warmup in runcard {0}".format(runcard.name))
        if not runcard.is_warmup():
            self._press_yes_to_continue("Warmup is not active in runcard")
        if continue_warmup and not runcard.is_continuation():
            self._press_yes_to_continue("Continue warmup is not active in runcard")
        if runcard.is_production():
            self._press_yes_to_continue("Production is active in runcard")

    # Checks for the grid storage system
    def check_for_existing_output_local(self, r, rname, baseSeed, producRun):
        """ Check whether given runcard already has output in the local run dir (looks for log files)
        """
        import re
        logger.debug("Checking whether runcard {0} has output for seeds that you are trying to submit...".format(rname))
        local_dir_name = self.get_local_dir_name(r, rname)
        files = os.listdir(local_dir_name)
        runcard = PROGRAMruncard(runcard_file=os.path.join(local_dir_name, r),
                                 logger=logger,
                                 grid_run=False,
                                 use_cvmfs=header.use_cvmfs_lhapdf,
                                 cvmfs_loc=header.cvmfs_lhapdf_location)
        runcard_id = runcard.runcard_dict_case_preserving["id"]
        logs = [f for f in files if f.endswith(".log") and runcard_id in f]
        logseed_regex = re.compile(r".s([0-9]+)\.[^\.]+$")
        existing_seeds = set([int(logseed_regex.search(i).group(1)) for i
                              in logs])
        submission_seeds = set(range(baseSeed, baseSeed+producRun))
        overlap = existing_seeds.intersection(submission_seeds)
        if overlap:
            logger.warning("Log files for seed(s) {0} already exist in run folders. Running will overwrite the logfiles already present.".format(" ".join(str(i) for i in overlap)))
            self._press_yes_to_continue(None)
        return


    def __check_pulled_warmup(self, success, tmpnm, warmup_extensions):
        if success:
            matches, sizes = self.tarw.check_filesizes(tmpnm, warmup_extensions)
            if len(matches)==0:
                logger.warning("No warmup file found on main Grid Storage")
                return False
            if any(size==0 for size in sizes):
                logger.warning("Empty warmup file found on Grid Storage")
                return False
        return success


    def _bring_warmup_files(self, runcard, rname, shell=False,
                            check_only=False, multichannel=False):
        """ Download the warmup file for a run to local directory
        extracts Vegas grid and log file and returns a list with their names

        check_only flag doesn't error out if the warmup doesn't exist, instead just returns
        and empty list for later use [intended for checkwarmup mode so multiple warmups can
        be checked consecutively.
        """

        from pyHepGrid.src.header import grid_warmup_dir, logger
        gridFiles = []
        suppress_errors = False
        if check_only:
            suppress_errors = True
        ## First bring the warmup .tar.gz
        outnm = self.warmup_name(runcard, rname)
        logger.debug("Warmup GFAL name: {0}".format(outnm))
        tmpnm = "tmp.tar.gz"
        logger.debug("local tmp tar name: {0}".format(tmpnm))
        success = self.gridw.bring(outnm, grid_warmup_dir, tmpnm, shell = shell,
                                   suppress_errors=suppress_errors)

        success ==  self.__check_pulled_warmup(success, tmpnm, warmup_extensions)


        if not success and not check_only:
            if self._press_yes_to_continue("Grid files failed to copy. Try backups from individual sockets?") == 0:
                backup_dir = os.path.join(grid_warmup_dir,outnm.replace(".tar.gz",""))
                backups = self.gridw.get_dir_contents(backup_dir)
                if len(backups) == 0:
                    logger.critical("No backups found. Did the warmup complete successfully?")
                else:
                    backup_files = backups.split()
                    for idx, backup in enumerate(backup_files):
                        logger.info("Attempting backup {1} [{0}]".format(idx+1, backup))
                        success = self.gridw.bring(backup, backup_dir, tmpnm, shell = shell, force=True)

                        success ==  self.__check_pulled_warmup(success, tmpnm, warmup_extensions)
                        if success:
                            break

        if not success:
            logger.critical("Grid files failed to copy. Did the warmup complete successfully?")
        else:
            logger.info("Grid files copied ok.")

        ## Now extract only the Vegas grid files and log file
        gridp = warmup_extensions
        gridp += [i+"_channel" for i in gridp]
        extractFiles = self.tarw.extract_extensions(tmpnm,
                                                    gridp+[".log",".txt","channels"])
        try:
            gridFiles = [i for i in extractFiles if ".log" not in i]
            logfile = [i for i in extractFiles if ".log" in i][0]
        except IndexError as e:
            if not check_only:
                logger.critical("Logfile not found. Did the warmup complete successfully?")
            else:
                return []


        if multichannel and len([i for i in gridFiles if "channels" in i]) ==0:
            logger.critical("No multichannel warmup found, but multichannel is set in the runcard.")
        elif multichannel:
            logger.info("Multichannel warmup files found.")
        if gridFiles == [] and not check_only: # No grid files found
            logger.critical("Grid files not found in warmup tarfile. Did the warmup complete successfully?")
        elif gridFiles == []:
            return []

        ## Tag log file as -warmup
        newlog = logfile + "-warmup"
        os.rename(logfile, newlog)
        # Remove temporary tar files
        os.remove(tmpnm)
        gridFiles.append(newlog)
        # Make sure access to the file is correct!
        for i in gridFiles:
            util.spCall(["chmod", "a+wrx", i])
        return gridFiles

    def get_grid_from_stdout(self, jobid, jobinfo):
        from pyHepGrid.src.header import default_runfolder
        import re
        stdout = "\n".join(self.cat_job(jobid, jobinfo, store=True))

        try:
            gridname = [i for i in stdout.split("\n") if "Writing grid" in i][0].split()[-1].strip()
            logger.info("Grid name from stdout: {0}".format(gridname))
        except IndexError as e:
            logger.critical("No grid filename found in stdout logs. Did the warmup write a grid?")

        result = re.search('vegas warmup to stdout(.*)End', stdout, flags=re.S) # Thanks StackOverflow

        try:
            grid = result.group(1)
        except IndexError as e:
            logger.critical("No grid found in stdout logs. Did the warmup write a grid?")

        logger.info("Grid extracted successfully")
        if default_runfolder is None:
            base = header.warmup_base_dir
        else:
            base = header.default_runfolder

        outloc = os.path.join(base, jobinfo["runfolder"], jobinfo["runcard"])
        grid_fname = os.path.join(outloc, gridname)
        os.makedirs(outloc, exist_ok=True)
        if os.path.exists(grid_fname):
            self._press_yes_to_continue("  \033[93m WARNING:\033[0m Grid file already exists at {0}. do you want to overwrite it?".format(grid_fname))
        with open(grid_fname, "w") as gridfile:
            gridfile.write(grid)
        logger.info("Grid written locally to {0}".format(os.path.relpath(grid_fname)))

    def check_runcard_multichannel(self, runcard_obj):
        try:
            multichannel_val = runcard_obj.runcard_dict["run"]["multi_channel"]
            if multichannel_val.lower() == ".true.":
                logger.info("Multichannel switched ON in runcard")
                multichannel=True
            else:
                multichannel=False
                logger.info("Multichannel switched OFF in runcard")
        except KeyError as e:
            multichannel = False
            logger.info("Multichannel not enabled in runcard")
        return multichannel

    ### Initialisation functions
    def _exe_fullpath(self, executable_src_dir, executable_exe):
        return os.path.join(executable_src_dir, "driver", executable_exe)

    def init_single_local_warmup(self, runcard, tag, continue_warmup=False,
                                 provided_warmup=False):
        import shutil
        from pyHepGrid.src.header import executable_src_dir, executable_exe, runcardDir, slurm_kill_exe
        run_dir = self.get_local_dir_name(runcard, tag)
        os.makedirs(run_dir, exist_ok=True)
        stdoutdir = self.get_stdout_dir_name(run_dir)
        os.makedirs(stdoutdir, exist_ok=True) # directory for slurm stdout files
        path_to_exe_full = self._exe_fullpath(executable_src_dir, executable_exe)
        shutil.copy(path_to_exe_full, run_dir)
        runcard_file = os.path.join(runcardDir, runcard)
        runcard_obj = PROGRAMruncard(runcard_file, logger=logger, grid_run=False,
                                     use_cvmfs=header.use_cvmfs_lhapdf,
                                     cvmfs_loc=header.cvmfs_lhapdf_location)
        self._check_warmup(runcard_obj, continue_warmup)
        logger.debug("Copying runcard {0} to {1}".format(runcard_file, run_dir))
        shutil.copy(runcard_file, run_dir)
        shutil.copy(slurm_kill_exe, run_dir)
        if provided_warmup:
            # Copy warmup to rundir
            match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(), provided_warmup)
            shutil.copy(match, run_dir)
        if runcard_obj.is_continuation():
            # Assert warmup is present in dir. Will error out if not
            if continue_warmup:
                match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(), run_dir)

    def init_warmup(self, provided_warmup=None, continue_warmup=False,
                    local=False):
        """ Initialises a warmup run. An warmup file can be provided and it will be
        added to the .tar file sent to the grid storage.
        Steps are:
            1 - tar up executable, runcard and necessary files
            2 - sent it to the grid storage
        """
        from shutil import copy
        import tempfile
        from pyHepGrid.src.header import executable_src_dir, executable_exe, logger
        from pyHepGrid.src.header import runcardDir as runFol

        if local:
            self.init_local_warmups(provided_warmup=provided_warmup,
                                    continue_warmup=continue_warmup)
            return
        origdir = os.path.abspath(os.getcwd())
        tmpdir = tempfile.mkdtemp()

        # if provided warmup is a relative path, ensure we have the full path
        # before we change to the tmp directory
        if provided_warmup:
            if provided_warmup[0] != "/":
                provided_warmup = "{0}/{1}".format(origdir, provided_warmup)

        os.chdir(tmpdir)

        logger.debug("Temporary directory: {0}".format(tmpdir))

        rncards, dCards = util.expandCard()
        path_to_exe_full = self._exe_fullpath(executable_src_dir,
                                              executable_exe)
        if not os.path.isfile(path_to_exe_full):
            logger.critical("Could not find executable at {0}".format(path_to_exe_full))
        copy(path_to_exe_full, os.getcwd())
        files = [executable_exe]
        for idx, i in enumerate(rncards):
            logger.info("Initialising {0} [{1}/{2}]".format(i, idx+1, len(rncards)))
            local = False
            warmupFiles = []
            # Check whether warmup/production is active in the runcard
            runcard_file = os.path.join(runFol, i)

            if not os.path.isfile(runcard_file):
                self._press_yes_to_continue("Could not find runcard {0}".format(i), error="Could not find runcard")
            runcard_obj = PROGRAMruncard(runcard_file, logger=logger,
                                         use_cvmfs=header.use_cvmfs_lhapdf,
                                         cvmfs_loc=header.cvmfs_lhapdf_location)
            self._check_warmup(runcard_obj, continue_warmup)
            multichannel = self.check_runcard_multichannel(runcard_obj)
            if provided_warmup:
                # Copy warmup to current dir if not already there
                match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(),
                                                          provided_warmup)
                files += [match]
            rname = dCards[i]
            tarfile = i + rname + ".tar.gz"
            copy(os.path.join(runFol, i), os.getcwd())
            if self.overwrite_warmup:
                checkname = self.warmup_name(i, rname)
                if self.gridw.checkForThis(checkname, header.grid_warmup_dir):
                    logger.info("Warmup found in GFAL:{0}!".format(header.grid_warmup_dir))
                    warmup_files = self._bring_warmup_files(i, rname, shell=True,
                                                            multichannel=multichannel)
                    files += warmup_files
                    logger.info("Warmup files found: {0}".format(" ".join(i for i in warmup_files)))

            self.tarw.tarFiles(files + [i], tarfile)
            if self.gridw.checkForThis(tarfile, header.grid_input_dir): # Could we cache this? Just to speed up ini
                logger.info("Removing old version of {0} from Grid Storage".format(tarfile))
                self.gridw.delete(tarfile, header.grid_input_dir)
            logger.info("Sending {0} to gfal {1}/".format(tarfile, header.grid_input_dir))
            self.gridw.send(tarfile, header.grid_input_dir, shell=True)
            if not local:
                for j in warmupFiles:
                    os.remove(j)
            os.remove(i)
            os.remove(tarfile)
        os.remove(executable_exe)
        os.chdir(origdir)

    def init_single_local_production(self, runcard, tag, provided_warmup=False):
        """ Initialise single production run for the local environment. Can probably be
        more tightly integrated with the warmup equivalent in future - lots of shared code
        that can be refactored."""
        import shutil
        from pyHepGrid.src.header import executable_src_dir, executable_exe, runcardDir
        run_dir = self.get_local_dir_name(runcard, tag)
        os.makedirs(run_dir, exist_ok=True)
        stdoutdir = self.get_stdout_dir_name(run_dir)
        os.makedirs(stdoutdir, exist_ok=True)  # directory for slurm stdout files
        path_to_exe_full = self._exe_fullpath(executable_src_dir, executable_exe)
        shutil.copy(path_to_exe_full, run_dir)
        runcard_file = os.path.join(runcardDir, runcard)
        runcard_obj = PROGRAMruncard(runcard_file, logger=logger,
                                     use_cvmfs=header.use_cvmfs_lhapdf,
                                     cvmfs_loc=header.cvmfs_lhapdf_location)
        self._check_production(runcard_obj)
        logger.debug("Copying runcard {0} to {1}".format(runcard_file, run_dir))
        shutil.copy(runcard_file, run_dir)
        if provided_warmup:
            # Copy warmup to rundir
            match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(),
                                                      provided_warmup)
            shutil.copy(match, run_dir)
        else:
            # check warmup is in dir - check is case insensitive - be careful!
            rundirfiles = [i.lower() for i in os.listdir(run_dir)]
            if runcard_obj.warmup_filename() not in rundirfiles:
                logger.critical("No warmup found in run folder and no warmup provided manually")

    def init_production(self, provided_warmup=None, continue_warmup=False,
                        local=False):
        """ Initialises a production run. If a warmup file is provided
        retrieval step is skipped
        Steps are:
            0 - Retrieve warmup from the grid/local
            1 - tar up executable, runcard and necessary files
            2 - sent it to the grid storage
        """
        from shutil import copy
        import tempfile
        from pyHepGrid.src.header import runcardDir as runFol
        from pyHepGrid.src.header import executable_exe, executable_src_dir, logger

        if local:
            self.init_local_production(provided_warmup=provided_warmup)
            return

        rncards, dCards = util.expandCard()
        path_to_exe_full = self._exe_fullpath(executable_src_dir, executable_exe)

        origdir = os.path.abspath(os.getcwd())
        tmpdir = tempfile.mkdtemp()

        # if provided warmup is a relative path, ensure we have the full path
        # before we change to the tmp directory
        if provided_warmup:
            if provided_warmup[0] != "/":
                provided_warmup = "{0}/{1}".format(origdir, provided_warmup)

        os.chdir(tmpdir)
        logger.debug("Temporary directory: {0}".format(tmpdir))

        if not os.path.isfile(path_to_exe_full):
            logger.critical("Could not find executable at {0}".format(path_to_exe_full))
        copy(path_to_exe_full, os.getcwd())
        files = [executable_exe]
        for idx, i in enumerate(rncards):
            logger.info("Initialising {0} [{1}/{2}]".format(i, idx+1, len(rncards)))
            local = False
            # Check whether warmup/production is active in the runcard
            runcard_file = os.path.join(runFol, i)
            runcard_obj = PROGRAMruncard(runcard_file, logger=logger,
                                         use_cvmfs=header.use_cvmfs_lhapdf,
                                         cvmfs_loc=header.cvmfs_lhapdf_location)
            multichannel = self.check_runcard_multichannel(runcard_obj)
            self._check_production(runcard_obj)
            rname = dCards[i]
            tarfile = i + rname + ".tar.gz"
            copy(os.path.join(runFol, i), os.getcwd())
            if provided_warmup:
                match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(),
                                                          provided_warmup)
                warmupFiles = [match]
            elif header.provided_warmup_dir:
                match, local = self._get_local_warmup_name(runcard_obj.warmup_filename(),
                                                          header.provided_warmup_dir)
                warmupFiles = [match]
            else:
                logger.info("Retrieving warmup file from grid")
                warmupFiles = self._bring_warmup_files(i, rname, shell=True, multichannel=multichannel)
            self.tarw.tarFiles(files + [i] + warmupFiles, tarfile)
            if self.gridw.checkForThis(tarfile, header.grid_input_dir):
                logger.info("Removing old version of {0} from Grid Storage".format(tarfile))
                self.gridw.delete(tarfile, header.grid_input_dir)
            logger.info("Sending {0} to GFAL {1}/".format(tarfile, header.grid_input_dir))
            self.gridw.send(tarfile, header.grid_input_dir, shell=True)
            if local:
                util.spCall(["rm", i, tarfile])
            else:
                util.spCall(["rm", i, tarfile] + warmupFiles)
        os.remove(executable_exe)
        os.chdir(origdir)

    def _get_local_warmup_name(self, matchname, provided_warmup):
        from shutil import copy
        exclude_patterns = [".txt", ".log"]
        if os.path.isdir(provided_warmup):
            matches = []
            potential_files = os.listdir(provided_warmup)
            for potfile in potential_files:
                if potfile.lower().startswith(matchname) \
                    and not any(potfile.endswith(p) for p in exclude_patterns):
                    matches.append(potfile)
            if len(matches) > 1:
                logger.critical("Multiple warmup matches found in {1}: {0}".format(" ".join(i for i in matches), provided_warmup))
            elif len(matches) ==0 :
                logger.critical("No warmup matches found in {0}.".format(provided_warmup))
            else:
                match = os.path.join(provided_warmup, matches[0])
        else:
            match = provided_warmup
        logger.info("Using warmup {0}".format(match))
        if not match in os.listdir(sys.path[0]):
            local_match = False
            copy(match, os.path.basename(match))
            match = os.path.basename(match)
        else:
            local_match = True
        return match, local_match

    def check_warmup_files(self, db_id, rcard, resubmit=False):
        """ Provides stats on whether a warmup file exists for a given run and optionally
        resubmit if absent"""
        from shutil import copy
        import tempfile
        import tarfile
        from pyHepGrid.src.header import logger

        origdir = os.path.abspath(os.getcwd())
        tmpdir = tempfile.mkdtemp()

        os.chdir(tmpdir)
        logger.debug("Temporary directory: {0}".format(tmpdir))
        rncards, dCards = util.expandCard()
        tags = ["runcard", "runfolder"]
        runcard_info = self.dbase.list_data(self.table, tags, db_id)[0]
        runcard = runcard_info["runcard"]
        rname = runcard_info["runfolder"]
        try:
            warmup_files = self._bring_warmup_files(runcard, rname,
                                                    check_only=True, shell=True)
            if warmup_files == []:
                status = "\033[93mMissing\033[0m"
            else:
                status = "\033[92mPresent\033[0m"
        except tarfile.ReadError as e:
            status = "\033[91mCorrupted\033[0m"
        run_id = "{0}-{1}:".format(runcard, rname)
        logger.info("[{0}] {2:55} {1:>20}".format(db_id, status, run_id))
        os.chdir(origdir)

        if resubmit and "Present" not in status:
            done, wait, run, fail, unk = self.stats_job(db_id, do_print=False)
            if run+wait>0:  # Be more careful in case of unknown status
                logger.warning("Job still running. Not resubmitting for now")
            else:
                # Need to override dictCard for single job submission
                expandedCard = ([runcard], {runcard: rname})
                logger.info("Warmup not found and job ended. Resubmitting to ARC")
                from pyHepGrid.src.runArcjob import runWrapper
                runWrapper(rcard, expandedCard=expandedCard)


def _init_Sherpa_single(warmup_dir):
    origdir = os.path.abspath(os.getcwd())
    os.chdir(warmup_dir)
    os.system("Sherpa INIT_ONLY=1")
    os.chdir(origdir)

class HEJ(ProgramInterface):

    def _exe_fullpath(self, executable_src_dir, executable_exe):
        return os.path.join(executable_src_dir, executable_exe)

    def warmup_name(self, runcard, rname):
        out = "{0}+{1}.tar.gz".format(runcard, rname)
        return out

    def output_name(self, runcard, rname, seed):
        out = "output-{0}-{1}-{2}.tar.gz".format(runcard, rname, str(seed))
        return out

    def _init_Sherpa(self,warmup_base,rncards):
        import multiprocessing as mp
        warmup_dirs = []
        for idx, i in enumerate(rncards):
            warmup_dir = warmup_base + i.split("-")[0] + "/"
            if not os.path.isdir(warmup_dir+"Process"):
                warmup_dirs.append(warmup_dir)
        pool = mp.Pool( mp.cpu_count()-5 )
        pool.map(_init_Sherpa_single, warmup_dirs, chunksize=1)

    def init_production(self, provided_warmup=None, continue_warmup=False,
                        local=False):
        """ Initialises a production run. If a warmup file is provided
        retrieval step is skipped
        Steps are:
            0 - Retrieve warmup from the grid/local
            1 - tar up executable, runcard and necessary files
            2 - sent it to the grid storage
        """
        import tempfile
        from pyHepGrid.src.header import runcardDir as runFol
        from pyHepGrid.src.header import executable_exe, executable_src_dir, grid_input_dir

        if local:
            self.init_local_production(provided_warmup=provided_warmup)
            return

        rncards, dCards = util.expandCard()
        path_to_exe_full = self._exe_fullpath(executable_src_dir, executable_exe)

        origdir = os.path.abspath(os.getcwd())
        tmpdir = tempfile.mkdtemp()

        # if provided warmup is a relative path, ensure we have the full path
        # before we change to the tmp directory
        if provided_warmup:
            if provided_warmup[0] != "/":
                provided_warmup = "{0}/{1}".format(origdir, provided_warmup)

        if provided_warmup:
            warmup_base = provided_warmup
        elif header.provided_warmup_dir:
            warmup_base = header.provided_warmup_dir
        else:
            # print("Retrieving warmup file from grid")
            # warmupFiles = self._bring_warmup_files(i, dCards[i], shell=True)
            logger.critical("Retrieving warmup file from grid: Not implemented")
        # setup LHAPDF
        if header.use_cvmfs_lhapdf:
            os.environ['LHAPDF_DATA_PATH'] = header.cvmfs_lhapdf_location
        # create Process dir in Sherpa
        self._init_Sherpa(warmup_base,rncards)

        os.chdir(tmpdir)
        logger.debug("Temporary directory: {0}".format(tmpdir))

        # if not os.path.isfile(path_to_exe_full):
        #     logger.critical("Could not find executable at {0}".format(path_to_exe_full))
        # copy(path_to_exe_full, os.getcwd())
        # files = [executable_exe]
        for idx, i in enumerate(rncards):
            local = False

            tarfile = i +"+"+ dCards[i] + ".tar.gz"
            base_folder = i.split("-")[0] + "/"
            logger.info("Initialising {0} to {1} [{2}/{3}]".format(i, tarfile, idx+1, len(rncards)))

            # runcards
            run_dir = runFol + base_folder
            runFiles = [dCards[i]+".yml"]
            for f in runFiles:
                os.system("cp -r "+run_dir+f+" "+tmpdir)

            # warmup files
            warmupFiles = ["Process", "Run.dat", "Results.db"]
            for f in warmupFiles:
                os.system("cp -r "+warmup_base+base_folder+f+" "+tmpdir)

            # tar up & send to grid storage
            self.tarw.tarFiles(warmupFiles+runFiles, tarfile)

            if self.gridw.checkForThis(tarfile, grid_input_dir):
                logger.info("Removing old version of {0} from Grid Storage".format(tarfile))
                self.gridw.delete(tarfile, grid_input_dir)
            logger.info("Sending {0} to {1}".format(tarfile, grid_input_dir))
            self.gridw.send(tarfile, grid_input_dir, shell=True)

        # clean up afterwards
        os.chdir(origdir)
        os.system("rm -r "+tmpdir)
