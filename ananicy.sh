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
# Initialisation
DIR_CACHE=/run/ananicy/
[ -d "$DIR_CACHE" ] || mkdir -p "$DIR_CACHE"

DIR_CONFIGS=/etc/ananicy.d/
[ -d "$DIR_CONFIGS" ] || ERRO "Config dir $DIR_CONFIGS doesn't exist!"

################################################################################
# Return specified line of file, ignore comments
read_line_slow(){
    FILE=$1 NUM=$2 LINE="$(head -n $NUM $FILE | tail -n 1)"
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

################################################################################
# Nice handler for process name
DIR_CACHE_NICE="$DIR_CACHE/NICE"
wrapper_renice(){
    [ -d "$DIR_CACHE_NICE" ] || mkdir -p "$DIR_CACHE_NICE"
    export NAME="$1" NICE="$2"
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
    [ -d "$DIR_CACHE_IONICE" ] || mkdir -p "$DIR_CACHE_IONICE"
    export NAME="$1" IOCLASS="$2" IONICE="$3"
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

################################################################################
# Main process
if [ "$1" == "start" ]; then
    [ "$UID" == "0" ] || ERRO "Script must be runned as root!"
    INFO "Start main process"
    while true; do
        for cache_line in "${RULE_CACHE[@]}"; do
            NAME="" NICE="" IOCLASS="" IONICE=""
            for COLUMN in $cache_line; do
                if   echo "$COLUMN" | grep -q 'NAME='; then
                    NAME="$(echo $COLUMN | cut -d'=' -f2)"
                elif echo "$COLUMN" | grep -q 'NICE='; then
                    NICE="$(echo $COLUMN | cut -d'=' -f2)"
                elif echo "$COLUMN" | grep -q 'IONICE='; then
                    IONICE="$(echo $COLUMN | cut -d'=' -f2)"
                elif echo "$COLUMN" | grep -q 'IOCLASS='; then
                    IOCLASS="$(echo $COLUMN | cut -d'=' -f2)"
                fi
            done
            if [ ! -z "$NAME" ]; then
                if [ ! -z "$NICE" ]; then
                    wrapper_renice "$NAME" "$NICE"
                fi
                if [ ! -z "$IOCLASS" ]; then
                    wrapper_ionice "$NAME" "$IOCLASS" "$IONICE"
                elif [ ! -z "$IONICE" ]; then
                    wrapper_ionice "$NAME" "NULL" "$IONICE"
                fi
            fi
        done
        sleep 60
    done
elif [ "$1" == "dump" ]; then
    if [ "$2" == "rule_cache" ]; then
        for cache_line in "${RULE_CACHE[@]}"; do
            echo "$cache_line"
        done
    fi
fi
