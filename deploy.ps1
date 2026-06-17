param(
    [string]$Message = "Update"
)

Write-Host "📦 Committing..." -ForegroundColor Cyan
git add -A
git commit -m $Message
git push

Write-Host "🚀 Deploying to Firebase..." -ForegroundColor Cyan
firebase deploy --only hosting

Write-Host "✅ Deploy เสร็จ! https://qa-tester-f005d.web.app" -ForegroundColor Green
