#!/bin/bash

env_root="$HOME/npm_codetraverse"

check_uv() {
    echo "ROOT - $env_root"
    if [ -d "$env_root/.venv/bin/uv" ]; then
        return 0
    else
        return 1
    fi
}

check_python() {
    python_path="$1"
    if command -v "$python_path" >/dev/null; then
        return 0
    else
        return 1
    fi
}

setup_env_helper() {
    python_path="$1"
    codetraverse_dir="$2"
    if check_uv "$env_root"; then
        echo "UV INSTALLED"
    else
        echo "INSTALLING UV (Not system wide)"
        if check_python "$python_path"; then
            if [ ! -d "$env_root/tmp_env" ]; then
                "$python_path" -m venv "$env_root/tmp_env"
                "$env_root/tmp_env/bin/python" -m pip install uv
            fi
            cd "$env_root"
            if [ ! -f "$env_root/pyproject.toml" ]; then
                "$env_root/tmp_env/bin/uv" init
            fi
            if [ ! -d "$env_root/.venv" ]; then
                "$env_root/tmp_env/bin/uv" venv "$env_root/.venv"
            fi
            "$env_root/tmp_env/bin/uv" add -r "$codetraverse_dir/codetraverse/requirements.txt"
            echo "SETUP FINISHED"
            exit 0
        else
            echo "VALID PYTHON PATH NOT PROVIDED. ABORTING"
            exit 1
        fi
    fi
}

setup_env() {
    python_path="$1"
    codetraverse_dir="$2"
    setup_env_helper "$python_path" "$codetraverse_dir"
}
setup_env "$1" "$2"
