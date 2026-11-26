@echo off
chcp 65001 >nul
REM ============================================================
REM  一键推送到 GitHub（在本文件所在目录双击运行）
REM  前提：安装 Git for Windows，并有一个 GitHub Personal Access Token
REM        （https://github.com/settings/tokens，需勾选 repo 权限）
REM ============================================================

set /p TOKEN=请粘贴你的 GitHub Personal Access Token 后回车: 
if "%TOKEN%"=="" (echo 未输入 token，退出。 & pause & exit /b 1)

set OWNER=hmk0407
set REPO=desktop-market-ticker

echo.
echo [1/3] 创建远程仓库...
curl -s -X POST https://api.github.com/user/repos ^
  -H "Authorization: Bearer %TOKEN%" ^
  -H "Accept: application/vnd.github+json" ^
  -d "{\"name\":\"%REPO%\",\"description\":\"Zero-dependency Windows desktop market ticker widget\",\"private\":false}" > repo_create.json
findstr /C:"\"full_name\"" repo_create.json >nul
if errorlevel 1 (
  echo 创建仓库失败或仓库已存在，响应如下：
  type repo_create.json
  echo.
  echo 如果是"已存在"，可跳过创建继续推送。
) else (
  echo 远程仓库创建成功。
)

echo.
echo [2/3] 配置 remote...
git remote remove origin 2>nul
git remote add origin https://%TOKEN%@github.com/%OWNER%/%REPO%.git

echo.
echo [3/3] 推送代码...
git branch -M main
git push -u origin main
if errorlevel 1 (
  echo 推送失败，请检查 token 权限（需 repo scope）。
) else (
  echo.
  echo 完成！仓库地址：https://github.com/%OWNER%/%REPO%
  echo 注意：remote 中明文保存了 token，推送成功后建议执行：
  echo   git remote set-url origin https://github.com/%OWNER%/%REPO%.git
)

del repo_create.json 2>nul
pause
