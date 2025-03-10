#!/usr/bin/env python3

#
# pyHepGrid.src.Backend Management classes
#
import pyHepGrid.src.utilities as util
import pyHepGrid.src.header as header
from pyHepGrid.src.Backend import Backend
import shutil
import os

class Arc(Backend):
    cmd_print = "arccat"
    cmd_get   = "arcget"
    cmd_kill  = "arckill"
    cmd_clean = "arcclean"
    cmd_stat  = "arcstat"
    cmd_renew = "arcrenew"

    def __init__(self, production=False, **kwargs):
        # Might not work on python2?
        super(Arc, self).__init__(**kwargs)
        if production:
            self.table = header.arcprodtable
        else:
            self.table = header.arctable
        self.production = production

    def __str__(self):
        retstr = "Arc"
        if self.production:
            retstr += " Production"
        return retstr

    def update_stdout(self):
        """ retrieves stdout of all running jobs and store the current state
        into its correspondent folder
        """
        fields = ["rowid", "jobid", "pathfolder", "runfolder"]
        dictC  = self._db_list(fields)
        for job in dictC:
            # Retrieve data from database
            jobid   = str(job['jobid'])
            rfold   = str(job['runfolder'])
            pfold   = str(job['pathfolder']) + "/" + rfold
            flnam   = pfold + "/stdout"
            # Create target folder if it doesn't exist
            if not os.path.exists(pfold):
                os.makedirs(pfold)
            cmd     = self.cmd_print + ' ' +  jobid.strip()
            # It seems script is the only right way to save data with arc
            stripcm = ['script', '-c', cmd, '-a', 'tmpscript.txt']
            mvcmd   = ['mv', 'tmpscript.txt', flnam]
            util.spCall(stripcm)
            util.spCall(mvcmd)

    def renew_proxy(self, jobids):
        """ renew proxy for a given job """
        for jobid in jobids:
            cmd = [self.cmd_renew, jobid.strip()]
            util.spCall(cmd)

    def kill_job(self, jobids, jobinfo):
        """ kills given job """
        self._press_yes_to_continue("  \033[93m WARNING:\033[0m You are about to kill the job!")

        if len(jobids) == 0:
            header.logger.critical("No jobids stored associated with this database entry, therefore nothing to kill.")

        for jobid_set in util.batch_gen(jobids, 150): # Kill in groups of 150 for speeeed
            stripped_set = [i.strip() for i in jobid_set]
            cmd = [self.cmd_kill, "-j", header.arcbase] + stripped_set
            header.logger.debug("job_kill batch length:{0}".format(len(stripped_set)))
            util.spCall(cmd)

    def clean_job(self, jobids):
        """ remove the sandbox of a given job (including its stdout!) from
        the arc storage """
        self._press_yes_to_continue("  \033[93m WARNING:\033[0m You are about to clean the job!")
        for jobid in jobids:
            cmd = [self.cmd_clean, "-j", header.arcbase, jobid.strip()]
            util.spCall(cmd)

    def cat_job(self, jobids, jobinfo, print_stderr = None, store = False):
        """ print stdandard output of a given job"""
        out = []
        for jobid in jobids:
            cmd = [self.cmd_print, "-j", header.arcbase, jobid.strip()]
            if print_stderr:
                cmd += ["-e"]
            if not store:
                util.spCall(cmd)
            else:
                out.append(util.getOutputCall(cmd))
        if store:
            return out


    def cat_log_job(self, jobids, jobinfo):
        """Sometimes the std output doesn't get updated
        but we can choose to access the logs themselves"""
        output_folder = ["file:///tmp/"]
        cmd_base =  ["arccp", "-i"]
        cmd_str = "cat /tmp/"
        for jobid in jobids:
            files = util.getOutputCall(["arcls", jobid]).split()
            logfiles = [i for i in files if i.endswith(".log")]
            for logfile in logfiles:
                cmd = cmd_base + [os.path.join(jobid, logfile)] + output_folder
                output = util.getOutputCall(cmd).split()
                for text in output:
                    if ".log" in text:
                        util.spCall((cmd_str + text).split())

    def bring_current_warmup(self, db_id):
        """ Sometimes we want to retrieve the warmup before the job finishes """
        output_folder = ["file:///tmp/"]
        cmd_base =  ["gfal-copy", "-v"]
        fields = ["pathfolder", "runfolder", "jobid"]
        data = self.dbase.list_data(self.table, fields, db_id)[0]
        runfolder =  data["runfolder"]
        finfolder =  pathfolder = data["pathfolder"] + "/" + runfolder + "/"
        if header.finalisation_script is not None:
            finfolder = header.default_runfolder
        jobids    =  data["jobid"].split()
        output_folder = ["file://" + finfolder]
        for jobid in jobids:
            cmd = cmd_base + [jobid + "/*.y*"] + output_folder
            util.spCall(cmd)
            cmd = cmd_base + [jobid + "/*.log"] + output_folder
            util.spCall(cmd)
        print("Warmup stored at {0}".format(finfolder))

    def status_job(self, jobids, verbose = False):
        """ print the current status of a given job """
        # for jobid in jobids:
        #     cmd = [self.cmd_stat, "-j", header.arcbase, jobid.strip()]
        #     if verbose:
        #         cmd += ["-l"]
        #     util.spCall(cmd)
        cmd = [self.cmd_stat, "-j", header.arcbase]
        print(header.arcbase)
        jobids = [jobid.strip() for jobid in jobids]
        cmd = cmd + jobids
        if verbose:
            cmd += ["-l"]
        util.spCall(cmd)

class Dirac(Backend):
    cmd_print = "dirac-wms-job-peek"
    cmd_kill  = "dirac-wms-job-kill"
    cmd_stat  = "dirac-wms-job-status"

    def __init__(self, **kwargs):
        super(Dirac, self).__init__(**kwargs)
        self.table = header.diractable

    def __str__(self):
        return "Dirac"

    def cat_job(self, jobids, jobinfo, print_stderr = None):
        print("Printing the last 20 lines of the last job")
        jobid = jobids[-1]
        cmd = [self.cmd_print, jobid.strip()]
        util.spCall(cmd)

    def status_job(self, jobids, verbose = False):
        """ query dirac on a job-by-job basis about the status of the job """
        self._multirun(self.do_status_job, jobids, header.finalise_no_cores)

    def do_status_job(self, jobid):
        """ multiproc wrapper for status_job """
        cmd = [self.cmd_stat, jobid]
        util.spCall(cmd, suppress_errors=True)
        return 0

    def get_status(self, status, date):
        output = set(util.getOutputCall(['dirac-wms-select-jobs','--Status={0}'.format(status),
                                       '--Owner={0}'.format(header.dirac_name),
                                       '--Maximum=0', # 0 lists ALL jobs, which is nice :)
                                       '--Date={0}'.format(date)]).split("\n")[-2].split(","))
        header.logger.debug(output)
        return output

    def stats_job(self, dbid):
        """ When using Dirac, instead of asking for each job individually
        we can ask for batchs of jobs in a given state and compare.
        """
        jobids = self.get_id(dbid)
        tags = ["runcard", "runfolder", "date"]
        runcard_info = self.dbase.list_data(self.table, tags, dbid)[0]

        try:
            self.__first_call_stats
        except AttributeError as e:
            self.__first_call_stats = False
        date = runcard_info["date"].split()[0]
        jobids_set = set(jobids)
        # Get all jobs in each state
        waiting_jobs = self.get_status('Waiting', date)
        done_jobs = self.get_status('Done', date)
        running_jobs = self.get_status('Running', date)
        fail_jobs = self.get_status('Failed', date)
        unk_jobs = self.get_status('Unknown', date)
        failed_jobs_set = jobids_set & fail_jobs
        done_jobs_set = jobids_set & done_jobs
        # Count how many jobs we have in each state
        fail = len(failed_jobs_set)
        done = len(done_jobs_set)
        wait = len(jobids_set & waiting_jobs)
        run = len(jobids_set & running_jobs)
        unk = len(jobids_set & unk_jobs)
        # Save done and failed jobs to the database
        status = len(jobids)*[0]
        for jobid in failed_jobs_set:
            status[jobids.index(jobid)] = self.cFAIL
        for jobid in done_jobs_set:
            status[jobids.index(jobid)] = self.cDONE
        self.stats_print_setup(runcard_info,dbid = dbid)
        total = len(jobids)
        self.print_stats(done, wait, run, fail, unk, total)
        self._set_new_status(dbid, status)


    def kill_job(self, jobids, jobinfo):
        """ kill all jobs associated with this run """
        self._press_yes_to_continue("  \033[93m WARNING:\033[0m You are about to kill all jobs for this run!")

        if len(jobids) == 0:
            header.logger.critical("No jobids stored associated with this database entry, therefore nothing to kill.")

        cmd = [self.cmd_kill] + jobids
        util.spCall(cmd)

class Slurm(Backend):
    def __init__(self, production=False, **kwargs):
        # Might not work on python2?
        super(Slurm, self).__init__(**kwargs)
        if production:
            self.table = header.slurmprodtable
        else:
            self.table = header.slurmtable
        self.production = production

    def __str__(self):
        retstr = "Slurm"
        if self.production:
            retstr += " Production"
        return retstr

    def _get_data_warmup(self, db_id):
        fields    =  ["runcard","runfolder", "jobid", "pathfolder"]
        data      =  self.dbase.list_data(self.table, fields, db_id)[0]
        warmup_output_dir = self.get_local_dir_name(data["runcard"],data["runfolder"])
        warmup_extensions = (".RRa", ".RRb", ".vRa", ".vRb", ".vBa", ".vBb",".log")
        warmup_files = [i for i in os.listdir(warmup_output_dir) if i.endswith(warmup_extensions)]
        header.logger.info("Found files: {0}".format(", ".join(warmup_files)))
        warmup_dir = os.path.join(header.warmup_base_dir,data["runfolder"])
        os.makedirs(warmup_dir,exist_ok=True)
        for warmfile in warmup_files:
            orig = os.path.join(warmup_output_dir, warmfile)
            new = os.path.join(warmup_dir, warmfile)
            shutil.copy(orig,new)
        header.logger.info("Warmup stored in {0}".format(warmup_dir))


    def _get_data_production(self, db_id):
        fields    =  ["runcard","runfolder", "jobid", "pathfolder"]
        data      =  self.dbase.list_data(self.table, fields, db_id)[0]
        production_output_dir = self.get_local_dir_name(data["runcard"],data["runfolder"])
        dat_files = [i for i in os.listdir(production_output_dir)
                        if i.endswith(".dat")]
        log_files = [i for i in os.listdir(production_output_dir)
                        if i.endswith(".log")]
        header.logger.info(dat_files, data["pathfolder"])
        production_dir = os.path.join(header.production_base_dir,data["runfolder"])
        os.makedirs(production_dir,exist_ok=True)
        results_folder = production_dir
        os.makedirs(results_folder, exist_ok=True)
        for prodfile in dat_files:
            orig = os.path.join(production_output_dir, prodfile)
            new = os.path.join(results_folder, prodfile)
            shutil.copy(orig,new)
        log_folder = os.path.join(results_folder,"log")
        os.makedirs(log_folder, exist_ok=True)
        for logfile in log_files:
            orig = os.path.join(production_output_dir, logfile)
            new = os.path.join(log_folder, logfile)
            shutil.copy(orig,new)


    def cat_log_job(self, jobids, jobinfo, *args, **kwargs):
        import re
        import glob
        run_dir = self.get_local_dir_name(jobinfo["runcard"],jobinfo["runfolder"])
        log_files = [i for i in os.listdir(run_dir) if i.endswith(".log")]

        if jobinfo["iseed"] is None:
            jobinfo["iseed"] = 1
        expected_seeds = set(range(int(jobinfo["iseed"]),int(jobinfo["iseed"])+int(jobinfo["no_runs"])))

        logseed_regex = re.compile(r".s([0-9]+)\.[^\.]+$")
        logseeds_in_dir = set([int(logseed_regex.search(i).group(1)) for i
                               in glob.glob('{0}/*.log'.format(run_dir))])
        seeds_to_print = (logseeds_in_dir.union(expected_seeds))

        cat_logs = []
        for log_file in log_files:
            for seed in seeds_to_print:
                if ".s{0}.".format(seed) in log_file:
                    cat_logs.append(log_file)
                    seeds_to_print.remove(seed)
                    break

        for log in cat_logs:
            cmd = ["cat", os.path.join(run_dir,log)]
            util.spCall(cmd)



    def get_status(self, jobid, status):
        stat = len([i for i in util.getOutputCall(["squeue", "-j{0}".format(jobid),"-r","-t",status],
                                                  suppress_errors=True).split("\n")[1:]
                    if "error" not in i]) #strip header from results
        if stat >0:
            stat = stat-1
        return stat


    def stats_job(self, dbid):
        tags = ["runcard", "runfolder", "date"]
        jobids = self.get_id(dbid) # only have one array id for SLURM
        runcard_info = self.dbase.list_data(self.table, tags, dbid)[0]
        running, waiting, fail, tot = 0,0,0,0
        for jobid in jobids:
            running += self.get_status(jobid,"R")
            waiting += self.get_status(jobid,"PD")
            fail += self.get_status(jobid,"F")+self.get_status(jobid,"CA")
            tot += self.get_status(jobid,"all")
        done = tot-fail-waiting-running
        self.stats_print_setup(runcard_info,dbid = dbid)
        total = len(jobids)
        self.print_stats(done, waiting, running, fail, 0, tot)


    def cat_job(self, jobids, jobinfo, print_stderr = None, store = False):
        """ print standard output of a given job"""
        dir_name = self.get_stdout_dir_name(self.get_local_dir_name(jobinfo["runcard"],
                                                                    jobinfo["runfolder"]))
        # jobids = length 1 for SLURM jobs - just take the only element here
        jobid = jobids[0]
        output = []
        if jobinfo["jobtype"] == "Production" or "Socket" in jobinfo["jobtype"]:
            for subjobno in range(1,int(jobinfo["no_runs"])+1):
                stdoutfile=os.path.join(dir_name,"slurm-{0}_{1}.out".format(jobid,subjobno))
                if print_stderr:
                    stdoutfile = stdoutfile.replace(".out",".err")
                cmd = ["cat", stdoutfile]
                if not store:
                    util.spCall(cmd)
                else:
                    output.append(util.getOutputCall(cmd,suppress_errors=True))
        else:
            stdoutfile=os.path.join(dir_name,"slurm-{0}.out".format(jobid))
            if print_stderr:
                stdoutfile = stdoutfile.replace(".out",".err")
            cmd = ["cat", stdoutfile]
            if not store:
                util.spCall(cmd)
            else:
                output.append(util.getOutputCall(cmd,suppress_errors=True))
        if store:
            return output

    def kill_job(self,jobids, jobinfo):
        header.logger.debug(jobids, jobinfo)
        if len(jobids) == 0:
            header.logger.critical("No jobids stored associated with this database entry, therefore nothing to kill.")

        for jobid in jobids:
            util.spCall(["scancel",str(jobid)])
        # Kill the socket server if needed
        # if "Socket" in jobinfo["jobtype"]:
        #     hostname = header.server_host
        #     port  = jobinfo["jobtype"].split("=")[-1]
        #     self._press_yes_to_continue("  \033[93m WARNING:\033[0m Killing TMUX server for job at {0}:{1}".format(hostname,port))
        #     import pyHepGrid.src.socket_api as sapi
        #     sapi.socket_sync_str(hostname,port,b"bye!")


    def status_job(self, jobids, verbose = False):
        """ print the current status of a given job """
        running,waiting,fail,tot = 0,0,0,0
        for jobid in jobids:
            running += self.get_status(jobid,"R")
            waiting += self.get_status(jobid,"PD")
            fail += self.get_status(jobid,"F")+self.get_status(jobid,"CA")
            tot += self.get_status(jobid,"all")
        done = tot-fail-waiting-running
        total = len(jobids)
        self.print_stats(done, waiting, running, fail, 0, tot)



if __name__ == '__main__':
    from sys import version_info
    print("Test for pyHepGrid.src.backendManagement.py")
    print("Running with: Python ", version_info.major)
    print("This test needs to be ran at gridui")
    arc   = Arc()
    dirac = Dirac()
    slurm = Slurm()
    print("Instantiate classes")
