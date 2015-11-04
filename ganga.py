#!/usr/bin/env python 

"""A grid submission script using ganga"""

import sys,os

# Set environment variables

LFNDIR=sys.argv[8]
NNLOJETNAME = sys.argv[9]

if sys.argv[7] == 'True':
    warmup = True
elif sys.argv[7] == 'False':
    warmup = False
else:
    print "Arguments: ", sys.argv
    raise Exception('Invalid arguments passed to job')


os.environ["LFC_HOST"]="lfc.grid.sara.nl"
os.environ["LCG_CATALOG_TYPE"]="lfc"
os.environ["LFC_HOME"]=LFNDIR
os.environ["LCG_GFAL_INFOSYS"]="lcgbdii.gridpp.rl.ac.uk:2170"
lhapdf_path = os.path.join(os.getcwd(), "LHAPDF", "lib")
gcc_libpath = os.path.join(os.getcwd(), "gcc", "lib")
gcc_lib64path = os.path.join(os.getcwd(), "gcc", "lib64")
if "LD_LIBRARY_PATH" in os.environ:
  old_ldpath = os.environ["LD_LIBRARY_PATH"]
  os.environ["LD_LIBRARY_PATH"] = "%s:%s:%s:%s" % (gcc_libpath,gcc_lib64path,old_ldpath, lhapdf_path)
else:
  os.environ["LD_LIBRARY_PATH"] = "%s:%s:%s" % (gcc_libpath,gcc_lib64path,lhapdf_path)

gcc_PATH = os.path.join(os.getcwd(),"gcc","bin")
# PATH must always exist
old_PATH = os.environ["PATH"]
os.environ["PATH"] = "%s:%s" % (gcc_PATH,old_PATH)
lhapdf_sharepath = os.path.join(os.getcwd(),"LHAPDF","share","LHAPDF")
os.environ['LHAPATH']=lhapdf_sharepath
os.environ['LHA_DATA_PATH']=lhapdf_sharepath
os.environ['OMP_STACKSIZE']="999999"
if warmup:
    os.environ['OMP_NUM_THREADS']="16"
else:
    os.environ['OMP_NUM_THREADS']="1"
os.environ['CC']="gcc"
os.environ['CXX']="g++"

LFN='lfn:'+LFNDIR
SRM='srm://se01.dur.scotgrid.ac.uk/dpm/dur.scotgrid.ac.uk/home/pheno/morgan_dir/'

# SRM
#os.system('lcg-cp '+SRM+'input/local.tar.gz $PWD/local.tar.gz' )
# LFN
os.system('lcg-cp lfn:input/local.tar.gz local.tar.gz')
os.system('lcg-cp lfn:input/' + NNLOJETNAME + '.tar.gz ' + NNLOJETNAME + '.tar.gz')
os.system('tar -zxf local.tar.gz')
os.system('tar -zxf ' + NNLOJETNAME + '.tar.gz')
os.system('chmod +x ' + NNLOJETNAME )


# COMMAND GOES HERE
command = ''

command += './' + NNLOJETNAME + '  '
for var in sys.argv[1:5]:
    command += ' '+var
os.system('cp runcards/'+sys.argv[2]+' .') # copy runcard to working dir

# For debugging
command +=';echo $LD_LIBRARY_PATH'

print "executed command: ", command
print "sys.argv: ", sys.argv
os.system(command)

os.system('voms-proxy-info --all')
os.system('lfc-mkdir output')
# clear all unnecessary files for taring

if not warmup:
    os.system('rm *.RRa *.RRb *.vRa ' +  NNLOJET)
os.system('rm -rf LHAPDF/')
os.system('rm -rf runcards/')
os.system('rm -rf gcc/')
os.system('rm local.tar.gz')
os.system('rm TOT.*')
os.system('rm fort*')


# tar and send to grid storage

if warmup:
    config = sys.argv[2]+'-w'
    directory = 'warmup'
else:
    config = sys.argv[2]+'-'+sys.argv[4]
    directory = 'output'

output = 'output'+config+'.tar.gz'

os.system('tar -czf '+output+' *') 
os.system('lcg-cp $PWD/'+output+' '+SRM+directory+'/'+output)

#SRM 
#print 'lcg-cp $PWD/'+output+' '+SRM+directory+'/'+output
#os.system('lcg-rf '+SRM+directory+'/'+output+' -l '+LFN+'/'+directory+'/'+output) 
#print 'lcg-rf '+SRM+directory+'/'+output+' -l '+LFN+'/'+directory+'/'+output

#LFN

os.system('ls')
os.system('lcg-cr --vo pheno -l lfn:'+directory+'/output'+config+'.tar.gz file:$PWD/output'+config+'.tar.gz')
print 'lcg-cr --vo pheno -l lfn:'+directory+'/output'+config+'.tar.gz file:$PWD/output'+config+'.tar.gz'
