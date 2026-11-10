FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app

COPY dst_helper/ ./dst_helper/
COPY DST_Cooking_Data_v0_1/handbook/ ./DST_Cooking_Data_v0_1/handbook/
COPY DST_Cooking_Data_v0_1/data/ ./DST_Cooking_Data_v0_1/data/
COPY DST_Cooking_Data_v0_1/dst_cooking.sqlite ./DST_Cooking_Data_v0_1/dst_cooking.sqlite
COPY DST_Farming_v0_1/scripts/planner_core.py ./DST_Farming_v0_1/scripts/planner_core.py
COPY DST_Farming_v0_1/data/ ./DST_Farming_v0_1/data/
COPY assets/images/ ./assets/images/

USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3).close()"]
CMD ["python", "-m", "dst_helper", "--host", "0.0.0.0", "--port", "8765"]
