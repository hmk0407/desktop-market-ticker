@echo off
chcp 65001 >nul
REM ============================================================
REM  一键推送到 GitHub（双击本文件运行即可）
REM  前提：1) 已安装 Git for Windows
REM        2) 有一个 GitHub Personal Access Token，勾选 repo 权限
REM           生成地址：https://github.com/settings/tokens
REM ============================================================
setlocal EnableDelayedExpansion

set OWNER=hmk0407
set REPO=desktop-market-ticker

echo.
echo ============================================
echo   GitHub 一键推送  ^-^>  %OWNER%/%REPO%
echo ============================================
echo.
echo 请打开 https://github.com/settings/tokens
echo 生成 token 时勾选 [repo] 权限（含全部子项），复制后粘贴到下面。
echo.
set /p TOKEN=Token: 
if "!TOKEN!"=="" (echo 未输入 token，已退出。 & pause & exit /b 1)

echo.
echo [1/3] 创建远程仓库（若已存在会提示，不影响后续）...
(
echo {"name":"!REPO!","description":"Zero-dependency Windows desktop market ticker widget","private":false}
) > payload.json
curl -s -o repo_create.json -w "HTTP %%{http_code}\n" -X POST https://api.github.com/user/repos ^
  -H "Authorization: Bearer !TOKEN!" ^
  -H "Accept: application/vnd.github+json" ^
  -H "Content-Type: application/json" ^
  -d @payload.json

echo.
echo [2/3] 配置远程地址...
git remote remove origin 2>nul
git remote add origin https://!TOKEN!@github.com/!OWNER!/!REPO!.git

echo.
echo [3/3] 推送代码...
git branch -M main
git push -u origin main
set PUSH_RC=!errorlevel!

REM 推送完成后清除 remote 里明文保存的 token
git remote set-url origin https://github.com/!OWNER!/!REPO!.git 2>nul

del payload.json 2>nul
del repo_create.json 2>nul

echo.
if "!PUSH_RC!"=="0" (
  echo ========== 完成！==========
  echo 仓库地址：https://github.com/!OWNER!/!REPO!
) else (
  echo 推送失败。常见原因：
  echo   1) token 没勾 repo 权限
  echo   2) 仓库名被占用且不属于你
  echo 若仓库已存在，可在网页确认后重试本脚本。
)
echo.
pause
