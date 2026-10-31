; VoxStudio installer (NSIS 3). Build: makensis installer/VoxStudio.nsi  (payload in installer/payload)
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "1.0.0"
!endif

Name "VoxStudio"
OutFile "..\dist\VoxStudio-Setup-${VERSION}.exe"
InstallDir "$PROFILE\VoxStudio"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "VoxStudio ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "VoxStudio"
VIAddVersionKey "FileDescription" "VoxStudio - clone giong va doc kich ban"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "VoxStudio"

!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Cài đặt VoxStudio ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "VoxStudio: clone giọng nói, đọc kịch bản thành audio + phụ đề, chạy hoàn toàn trên máy bạn.$\r$\n$\r$\nYêu cầu:$\r$\n  • Windows 10/11 64-bit$\r$\n  • Card NVIDIA từ 8GB VRAM (khuyến nghị)$\r$\n  • Khoảng 15GB ổ đĩa trống, có Internet$\r$\n$\r$\nTrình cài sẽ tự tải thêm khoảng 8GB (Python, thư viện, model). Lần đầu mất 15–40 phút."
!insertmacro MUI_PAGE_WELCOME

!define MUI_DIRECTORYPAGE_TEXT_TOP "Chọn nơi cài VoxStudio. Nên chọn ổ SSD còn trống ít nhất 15GB (VD: D:\VoxStudio). Tránh thư mục được đồng bộ OneDrive."
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "VoxStudio đã sẵn sàng"
!define MUI_FINISHPAGE_TEXT "Mở VoxStudio bằng icon ngoài Desktop hoặc trong Start Menu.$\r$\n$\r$\nKhi có bản mới, app sẽ hiện nút 'Cập nhật ngay' — chỉ cần bấm."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Mở VoxStudio ngay"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Vietnamese"

Function LaunchApp
  Exec '"$SYSDIR\wscript.exe" "$INSTDIR\VoxStudio.vbs"'
FunctionEnd



Section "VoxStudio" SecMain
  AddSize 15000000
  SetOutPath "$INSTDIR"
  File /r "payload\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "DisplayName" "VoxStudio"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "DisplayIcon" "$INSTDIR\assets\icon.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio" "NoRepair" 1

  DetailPrint "Đang tải và cài Python, thư viện, model (cửa sổ cài đặt sẽ hiện ra, vui lòng chờ)..."
  ExecWait '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install.ps1"' $0

  ClearErrors
  FileOpen $1 "$INSTDIR\logs\install_status.txt" r
  FileRead $1 $2
  FileClose $1
  StrCpy $3 $2 4 3   ; bỏ BOM UTF-8
  ${If} $3 != "DONE"
    StrCpy $3 $2 4
  ${EndIf}
  ${If} $3 != "DONE"
    MessageBox MB_ICONEXCLAMATION "Cài đặt chưa hoàn tất (thường do mất mạng).$\r$\n$\r$\nMở thư mục $INSTDIR và chạy 'install.bat' để cài tiếp — các bước đã xong sẽ được bỏ qua."
  ${EndIf}
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\VoxStudio.lnk"
  Delete "$SMPROGRAMS\VoxStudio.lnk"
  RMDir /r "$INSTDIR\.venv"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\models"
  RMDir /r "$INSTDIR\cache"
  RMDir /r "$INSTDIR\tmp"
  RMDir /r "$INSTDIR\VoxCPM-src"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\scripts"
  RMDir /r "$INSTDIR\assets"
  RMDir /r "$INSTDIR\logs"
  Delete "$INSTDIR\*.py"
  Delete "$INSTDIR\*.bat"
  Delete "$INSTDIR\*.vbs"
  Delete "$INSTDIR\*.ps1"
  Delete "$INSTDIR\*.json"
  Delete "$INSTDIR\*.txt"
  Delete "$INSTDIR\*.md"
  Delete "$INSTDIR\.gitignore"
  Delete "$INSTDIR\Uninstall.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\VoxStudio"
  RMDir "$INSTDIR"
  MessageBox MB_ICONINFORMATION "Đã gỡ VoxStudio.$\r$\nGiọng đã lưu, dự án và file kết quả (voices, projects, outputs) vẫn được giữ trong:$\r$\n$INSTDIR"
SectionEnd
