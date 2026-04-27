# Sourced by every sbatch script. Centralizes env setup.
set -euo pipefail

module load uv

source /project/cil/rcc/envs/flex_damages_dev/bin/activate

export PROJECT_ROOT=/project/cil/home_dirs/scadavidsanchez/projects/ag-flex-damage-functions/flexdamage-v3
export SCRATCH_BASE=/scratch/midway3/cadavidsanchez/flex-damages

# Threading: make BLAS, MKL, OpenBLAS, NumExpr use all SLURM-assigned cores
# (pyfixest demeaning hits numpy which hits one of these)
_THREADS=${SLURM_CPUS_PER_TASK:-$(nproc 2>/dev/null || echo 1)}
export OMP_NUM_THREADS=$_THREADS
export MKL_NUM_THREADS=$_THREADS
export OPENBLAS_NUM_THREADS=$_THREADS
export NUMEXPR_NUM_THREADS=$_THREADS

cd "$PROJECT_ROOT"

echo "Host:             $(hostname)"
echo "Date:             $(date)"
echo "Python:           $(which python)"
echo "Python version:   $(python --version)"
echo "CPUs allocated:   ${SLURM_CPUS_PER_TASK:-unset}"
echo "Mem allocated:    ${SLURM_MEM_PER_NODE:-unset} MB"
echo "Thread env:       OMP=$OMP_NUM_THREADS MKL=$MKL_NUM_THREADS OBLAS=$OPENBLAS_NUM_THREADS"
echo "Project root:     $PROJECT_ROOT"
echo "Scratch base:     $SCRATCH_BASE"
