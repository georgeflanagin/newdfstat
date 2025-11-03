function dfstat
{
    export PYTHONPATH=/usr/local/hpclib
    python3.11 dfstat.py --zap --log-level 10 $@
}
