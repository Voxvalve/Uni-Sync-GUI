#!/bin/bash
set -e

# 1. Verification
if [ ! -f "icon.png" ]; then
    echo "❌ Error: 'icon.png' missing."
    exit 1
fi

if [ ! -f "uni_gui.py" ]; then
    echo "❌ Error: 'uni_gui.py' missing."
    echo "   Please save the python code as uni_gui.py in this folder."
    exit 1
fi

echo "🔹 Setting up environment..."
sudo dnf install -y python3-pip python3-tkinter python3-devel gcc wget fuse libappindicator-gtk3
pip3 install pyinstaller --upgrade

# 2. Build Directory
BUILD_DIR="UniSync_Build_Final"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp uni_gui.py "$BUILD_DIR/uni_control.py"
cp icon.png "$BUILD_DIR/"
cd "$BUILD_DIR"

echo "🔹 Compiling Python..."
python3 -m PyInstaller --onefile --windowed --name UniController --hidden-import=tkinter uni_control.py

echo "🔹 Creating AppImage Structure..."
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

if [ -f "dist/UniController" ]; then
    cp dist/UniController AppDir/usr/bin/
else
    echo "❌ Error: Binary compilation failed."
    exit 1
fi

cat << END > AppDir/uni-controller.desktop
[Desktop Entry]
Name=Uni-Sync Manager
Exec=UniController
Icon=uni-sync
Type=Application
Categories=Utility;
END

cp icon.png AppDir/usr/share/icons/hicolor/256x256/apps/uni-sync.png
cp icon.png AppDir/uni-sync.png
ln -s usr/bin/UniController AppDir/AppRun

# 3. Packaging
echo "🔹 Downloading AppImageTool..."
wget -N https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

echo "🔹 Generating AppImage..."
ARCH=x86_64 ./appimagetool-x86_64.AppImage AppDir

# 4. Finalizing
echo "🔹 Finalizing..."
# Move and rename the output to the main folder
mv Uni-Sync_Manager-x86_64.AppImage ../uni-sync_gui.AppImage

echo "✅ Success! File created: uni-sync_gui.AppImage"