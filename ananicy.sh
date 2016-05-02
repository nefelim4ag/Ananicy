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
# Global vars
DIR_CACHE=/run/ananicy/
DIR_CONFIGS=/etc/ananicy.d/
RUN_FREQ=15

################################################################################
# Return specified line of file, ignore comments
read_line_slow(){
    FILE=$1 NUM=$2 LINE="$(head -n $NUM $FILE | tail -n 1)"
    LINE="$(echo $LINE | tr -d '$()`')"
    echo "$LINE" | grep -q '#' && LINE="$(echo $LINE | cut -d'#' -f1)"
    echo "$LINE" | grep -q 'NAME=' || LINE=""
    echo "$LINE"
}

linecount(){ FILE="$1"; cat "$FILE" | wc -l; }

################################################################################
# Rule compilation
INFO "Compile rule files"

RULE_CACHE=()
CONFIGS=( $(find -P $DIR_CONFIGS -type f) )
[ "0" != "${#CONFIGS[@]}" ] || ERRO "Config dir: $DIR_CONFIGS are empty!"

for config in "${CONFIGS[@]}"; do
    LINE_COUNT=$(linecount "$config")
    for line_number in $(seq 1 $LINE_COUNT); do
        LINE="$(read_line_slow $config $line_number)"
        [ -z "$LINE" ] || RULE_CACHE=( "${RULE_CACHE[@]}" "$LINE" )
    done
done

[ "0" != "${#RULE_CACHE[@]}" ] || ERRO "No rule is enabled!"

show_cache(){
    for cache_line in "${RULE_CACHE[@]}"; do
        echo "$cache_line"
    done
}

trap "{ INFO Dump compiled rules; show_cache; }" SIGUSR1
################################################################################
# Nice handler for process name
DIR_CACHE_NICE="$DIR_CACHE/NICE"
wrapper_renice(){
    export NAME="$1" NICE="$2"
    [ -z $NICE ] && return
    [ -d "$DIR_CACHE_NICE" ] || mkdir -p "$DIR_CACHE_NICE"
    for pid in $( pgrep -w "$NAME" ); do
            LOCK="$DIR_CACHE_NICE/${NAME}.${pid}"
            [ ! -f "$LOCK" ] || OLD_NICE="$(cat $LOCK)"
            if [ "$OLD_NICE" != "$NICE" ]; then
                echo -en "$NAME\t"
                renice -n $NICE -p $pid && echo $NICE > $LOCK
            fi
    done
}

################################################################################
# IONice handler for process name
DIR_CACHE_IONICE="$DIR_CACHE/IONICE"
wrapper_ionice(){
    export NAME="$1" IOCLASS="$2" IONICE="$3"
    [ "$IOCLASS" == "NULL" ] && [ -z "$IONICE" ] && return
    [ -d "$DIR_CACHE_IONICE" ] || mkdir -p "$DIR_CACHE_IONICE"
    for pid in $( pgrep -w "$NAME" ); do
            if [ "$IOCLASS" != "NULL" ]; then
                LOCK="$DIR_CACHE_IONICE/${NAME}.${pid}.ioclass"
                [ ! -f "$LOCK" ] || OLD_CLASS="$(cat $LOCK)"
                if [ "$OLD_CLASS" != "$IOCLASS" ]; then
                    if ionice -c "$IOCLASS" -p "$pid"; then
                        echo "$IOCLASS" > "$LOCK"
                        INFO "Process $NAME ioclass: $IOCLASS"
                    fi
                fi
            fi
            if [ ! -z "$IONICE" ]; then
                LOCK="$DIR_CACHE_IONICE/${NAME}.${pid}.ionice"
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

check_root_rights(){
    [ "$UID" == "0" ] || ERRO "Script must be runned as root!"
}

pre_start_checks(){
    check_root_rights
    [ -d "$DIR_CACHE" ] || mkdir -p "$DIR_CACHE"
    [ -d "$DIR_CONFIGS" ] || ERRO "Config dir $DIR_CONFIGS doesn't exist!"
}

main_pid_get(){
    if systemctl -q is-active ananicy; then
        echo "$(systemctl status ananicy | grep PID | awk '{print $3}')"
    else
        ERRO "Ananicy services has stopped!"
    fi
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
        pre_start_checks
        INFO "Start main process"
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
