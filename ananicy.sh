#!/bin/bash
################################################################################
# Ananicy - is Another auto nice daemon, with community rules support
# Configs are placed under /etc/ananicy.d/

################################################################################
# Define some fuctions
INFO(){ echo -n "INFO: "; echo "$@" ;}
WARN(){ echo -n "WARN: "; echo "$@" ;}
ERRO(){ echo -n "ERRO: "; echo -n "$@" ; echo " Abort!"; exit 1;}

################################################################################
# Check DIR_CONFIGS
DIR_CONFIGS=/etc/ananicy.d/
INFO "Check $DIR_CONFIGS dir"
[ -d "$DIR_CONFIGS" ] || ERRO "Config dir $DIR_CONFIGS doesn't exist!"

################################################################################
# Load all rule file names
INFO "Search rules"
CONFIGS=( $(find -P $DIR_CONFIGS -type f) )
[ "0" != "${#CONFIGS[@]}" ] || ERRO "Config dir: $DIR_CONFIGS are empty!"

################################################################################
# Return specified line of file, ignore comments
read_line(){
    FILE="$1" NUM=$2 # Read line | remove unsafe symbols | remove comments
    LINE="$(head -n $NUM $FILE | tail -n 1 | tr -d '$()`' | cut -d'#' -f1)"
    echo "$LINE"
}

################################################################################
# Dedup rules
declare -A RULE_CACHE_TMP

for config in "${CONFIGS[@]}"; do
    LINE_COUNT=$(cat "$config" | wc -l)
    for line_number in $(seq 1 $LINE_COUNT); do
        LINE="$(read_line $config $line_number)"
        if [ ! -z "$LINE" ]; then
            NAME=""
            for COLUMN in $LINE; do
                case "$COLUMN" in
                    NAME=*)
                        NAME="$(echo $COLUMN | cut -d'=' -f2)"
                        [ -z "$NAME" ] && ERRO "$config:$line_number NAME are empty!"
                        ;;
                esac
            done
            RULE_CACHE_TMP["$NAME"]="$LINE"
        fi
    done
done

unset CONFIGS
################################################################################
# Compile rules
INFO "Compile rule files"
RULE_CACHE=()
for LINE in "${RULE_CACHE_TMP[@]}"; do
    case "$LINE" in
        *NAME=*)
            case "$LINE" in
                *NICE=*)    : ;;
                *IOCLASS=*) : ;;
                *IONICE=*)  : ;;
                *) LINE="" ;;
            esac
        ;;
        *) LINE="";
    esac
    [ -z "$LINE" ] || RULE_CACHE=( "${RULE_CACHE[@]}" "$LINE" )
done
unset RULE_CACHE_TMP

[ "0" != "${#RULE_CACHE[@]}" ] || ERRO "No rule is enabled!"

################################################################################
# Show cached information
show_cache(){
    INFO "Dump compiled rules"
    {
        for cache_line in "${RULE_CACHE[@]}"; do
            echo "$cache_line"
        done
    } | column -t
}

trap "{ show_cache; }" SIGUSR1
################################################################################
# Cache dir for save nice and ionice state of processes
DIR_CACHE=/run/ananicy/

################################################################################
# Nice handler for process name
wrapper_renice(){
    export NAME="$1" NICE="$2"
    [ -z $NICE ] && return

    DIR_CACHE_NICE="$DIR_CACHE/NICE"
    [ -d "$DIR_CACHE_NICE" ] || mkdir -p "$DIR_CACHE_NICE"

    for pid in $( pgrep -w "$NAME" ); do
        LOCK="$DIR_CACHE_NICE/${NAME}.${pid}"
        [ ! -f "$LOCK" ] || OLD_NICE="$(cat $LOCK)"
        if [ "$OLD_NICE" != "$NICE" ]; then
            INFO "Process $NAME cpu nice: $NICE"
            renice -n $NICE -p $pid &> /dev/null && echo $NICE > $LOCK
        fi
    done
}

################################################################################
# IONice handler for process name
wrapper_ionice(){
    export NAME="$1" IOCLASS="$2" IONICE="$3"
    [ "$IOCLASS" == "NULL" ] && [ -z "$IONICE" ] && return

    DIR_CACHE_IONICE="$DIR_CACHE/IONICE"
    [ -d "$DIR_CACHE_IONICE" ] || mkdir -p "$DIR_CACHE_IONICE"

    for pid in $( pgrep -w "$NAME" ); do
        LOCK="$DIR_CACHE_IONICE/${NAME}.${pid}.ioclass"
        if [ "$IOCLASS" != "NULL" ]; then
            [ ! -f "$LOCK" ] || OLD_CLASS="$(cat $LOCK)"
            if [ "$OLD_CLASS" != "$IOCLASS" ]; then
                if ionice -c "$IOCLASS" -p "$pid"; then
                    echo "$IOCLASS" > "$LOCK"
                    INFO "Process $NAME ioclass: $IOCLASS"
                fi
            fi
        fi
        LOCK="$DIR_CACHE_IONICE/${NAME}.${pid}.ionice"
        if [ ! -z "$IONICE" ]; then
            [ ! -f "$LOCK" ] || OLD_IONICE="$(cat $LOCK)"
            if [ "$OLD_IONICE" != "$IONICE" ]; then
                if ionice -n "$IONICE" -p "$pid"; then
                    echo "$IONICE" > "$LOCK"
                    INFO "Process $NAME ionice: $IONICE"
                fi
            fi
        fi
    done
}

check_root_rights(){ [ "$UID" == "0" ] || ERRO "Script must be runned as root!"; }

main_pid_get(){
    if systemctl -q is-active ananicy; then
        echo "$(systemctl status ananicy | grep PID | awk '{print $3}')"
    else
        ERRO "Ananicy services has stopped!"
    fi
}

check_schedulers(){
    for disk in /sys/class/block/*/queue/scheduler; do
        case "$(cat $disk)" in
            *'[cfq]'*) : ;;
            *)
                disk=$(echo $disk | sed 's/\/sys\/class\/block\///g' | sed 's/\/queue\/scheduler//g')
                WARN "Disk $disk not used cfq scheduler IOCLASS/IONICE will not work on it!"
            ;;
        esac
    done
}

show_help(){
    echo "$0 start - start daemon"
    echo "$0 dump rules cache - daemon will dump rules cache to stdout"
    echo "$0 dump rules parsed - generate and dump rules cache to stdout"
}

main_process(){
    for cache_line in "${RULE_CACHE[@]}"; do
        NAME="" NICE="" IOCLASS="NULL" IONICE=""
        for COLUMN in $cache_line; do
            case "$COLUMN" in
                NAME=*)    NAME="$(echo $COLUMN | cut -d'=' -f2)"    ;;
                NICE=*)    NICE="$(echo $COLUMN | cut -d'=' -f2)"    ;;
                IONICE=*)  IONICE="$(echo $COLUMN | cut -d'=' -f2)"  ;;
                IOCLASS=*) IOCLASS="$(echo $COLUMN | cut -d'=' -f2)" ;;
            esac
        done
        if [ ! -z "$NAME" ]; then
            wrapper_renice "$NAME" "$NICE"
            wrapper_ionice "$NAME" "$IOCLASS" "$IONICE"
        fi
    done
}

################################################################################
# Main process
case $1 in
    start)
        check_root_rights
        check_schedulers
        INFO "Start main process"
        RUN_FREQ=15
        while true; do
            main_process
            sleep $RUN_FREQ
        done
    ;;
    dump)
        case "$2" in
            rules)
                case "$3" in
                    cache)
                        check_root_rights
                        PID_MAIN="$(main_pid_get)"
                        kill -s SIGUSR1 $PID_MAIN
                    ;;
                    parsed) show_cache ;;
                    *) show_help ;;
                esac
            ;;
            *) show_help ;;
        esac
    ;;
    *) show_help ;;
esac
