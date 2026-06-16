import os
import re
import sys
import subprocess
import time
import shutil
from pathlib import Path
from config.genai_client import generate_content

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
APPS_DIR = Path.home() / "Desktop" / "JarvisApps"

def _strip_fences(text: str) -> str:
    """
    Aggressively extracts Kotlin code from a markdown-formatted or conversational response.
    Looks for the first detected Kotlin code block.
    """
    # Regex to find content between ```kotlin and ``` (or just ``` and ```)
    match = re.search(r"```(?:kotlin)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: if no fences, but starts with 'package', assume raw code
    if text.strip().startswith("package "):
        return text.strip()
        
    return text.strip()

def apk_builder(parameters: dict, player=None, speak=None) -> str:
    """
    Architects and generates Kotlin code for an Android app based on a user's description.
    Note: To actually compile the APK, the host system must have Android SDK and Gradle installed.
    """
    app_name = parameters.get("app_name", "JarvisApp")
    features = parameters.get("features", "")
    
    if not features:
        return "Please provide a description of the app features, sir."

    safe_name = re.sub(r"[^\w\-]", "", app_name).lower()
    project_dir = APPS_DIR / safe_name
    
    if player:
        player.write_log(f"Architecting Android app: {app_name}...")

    # 1. Create full Android directory structure
    app_dir = project_dir / "app"
    src_dir = app_dir / "src/main/java/com/jarvis/generated"
    res_dir = app_dir / "src/main/res/layout"
    val_dir = app_dir / "src/main/res/values"
    
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    # [NEW FIX]: Generate a basic layout XML to satisfy 'R' resolution
    layout_xml = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/main_layout"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:padding="16dp">
</LinearLayout>"""
    (res_dir / "activity_main.xml").write_text(layout_xml, encoding="utf-8")
    if player: player.write_log("Generated activity_main.xml placeholder")

    # 2. Generate Project Files (Gradle & Settings)
    settings_gradle = f'rootProject.name = "{app_name}"\ninclude ":app"'
    (project_dir / "settings.gradle").write_text(settings_gradle, encoding="utf-8")

    # [FIX 1]: Generate local.properties for absolute SDK path detection
    local_properties = "sdk.dir=C:\\\\AndroidSDK"
    (project_dir / "local.properties").write_text(local_properties, encoding="utf-8")
    if player: player.write_log("Generated local.properties with sdk.dir=C:\\AndroidSDK")

    # [NEW FIX]: Generate gradle.properties for AndroidX support (CRITICAL for modern builds)
    gradle_properties = "android.useAndroidX=true\nandroid.enableJetifier=true"
    (project_dir / "gradle.properties").write_text(gradle_properties, encoding="utf-8")
    if player: player.write_log("Generated gradle.properties with AndroidX enabled")

    # [FIX 5]: Clean Architecture with stable buildscript pattern
    root_build_gradle = """buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath "com.android.tools.build:gradle:8.1.0"
        classpath "org.jetbrains.kotlin:kotlin-gradle-plugin:1.8.10"
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}"""
    (project_dir / "build.gradle").write_text(root_build_gradle, encoding="utf-8")

    app_build_gradle = """apply plugin: 'com.android.application'
apply plugin: 'org.jetbrains.kotlin.android'

android {
    namespace 'com.jarvis.generated'
    compileSdk 33
    defaultConfig {
        applicationId "com.jarvis.generated"
        minSdk 24
        targetSdk 33
        versionCode 1
        versionName "1.0"
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
    
    kotlinOptions {
        jvmTarget = '17'
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.10.1'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.9.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
}"""
    (app_dir / "build.gradle").write_text(app_build_gradle, encoding="utf-8")

    # 3. Generate Basic Resources (colors, strings, themes)
    (val_dir / "colors.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="purple_200">#FFBB86FC</color>
    <color name="purple_500">#FF6200EE</color>
    <color name="teal_200">#FF03DAC5</color>
    <color name="black">#FF000000</color>
    <color name="white">#FFFFFFFF</color>
</resources>""", encoding="utf-8")

    (val_dir / "themes.xml").write_text("""<resources>
    <style name="Theme.JarvisApp" parent="Theme.MaterialComponents.DayNight.DarkActionBar">
        <item name="colorPrimary">@color/purple_500</item>
        <item name="colorSecondary">@color/teal_200</item>
    </style>
</resources>""", encoding="utf-8")

    # 4. Generate Kotlin Code via OpenCode Zen
    system_instruction = """You are an Expert Android Developer.
Output ONLY the raw Kotlin code for a complete MainActivity.kt file.
Do NOT include any explanation, conversational text, or markdown fences in your output.
CRITICAL RULE: The package name MUST be EXACTLY: package com.jarvis.generated
Rules:
- Package name must be: com.jarvis.generated
- Use 'R.layout.activity_main' as the content view in onCreate.
- Use 'findViewById<LinearLayout>(R.id.main_layout)' to get the root layout.
- Create all UI elements (Buttons, Views) PROGRAMMATICALLY in Kotlin code.
- Add elements to the main layout using layout.addView().
- Ensure all imports (Toast, Color, Button, etc.) are included.
- Output a SINGLE cohesive block of code."""

    code_prompt = f"Write the MainActivity.kt code for an app named '{app_name}'. Features: {features}."

    try:
        if player:
            player.write_log("Architecting Kotlin code via OpenCode Zen...")
            
        response = generate_content(
            model="deepseek-v4-flash-free",
            contents=code_prompt,
            config={"system_instruction": system_instruction},
            provider="opencode"
        )
        
        kotlin_code = _strip_fences(response)
        
        # [CRITICAL FIX]: Force the package name to match the Manifest, regardless of AI output
        kotlin_code = re.sub(r"^package\s+[\w\.]+", "package com.jarvis.generated", kotlin_code, count=1, flags=re.MULTILINE)
        
        # 5. Save the generated code
        kotlin_file_path = src_dir / "MainActivity.kt"
        kotlin_file_path.write_text(kotlin_code, encoding="utf-8")
        
        # 6. Generate AndroidManifest.xml
        manifest_path = app_dir / "src/main/AndroidManifest.xml"
        manifest_content = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:label="{app_name}"
        android:supportsRtl="true"
        android:theme="@style/Theme.JarvisApp">
        <activity
            android:name="com.jarvis.generated.MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>"""
        manifest_path.write_text(manifest_content, encoding="utf-8")

        msg = f"SUCCESS: Full Android project for '{app_name}' has been architected.\nSaved to: {project_dir}\n\n"
        
        if player:
            player.write_log("Starting APK Compilation (Heavy Lifting)...")

        # 7. Attempt Auto-Compilation
        try:
            # Robust Gradle Execution
            gradle_bin_path = os.environ.get("GRADLE_HOME", r"C:\Gradle\gradle-8.1.1")
            gradle_bin = os.path.join(gradle_bin_path, "bin", "gradle.bat")
            
            if not os.path.exists(gradle_bin):
                gradle_bin = shutil.which("gradle")
                if not gradle_bin:
                    msg += f"Architecture complete. Note: 'gradle' was not found. Please set GRADLE_HOME or add to PATH."
                    if player: player.write_log("Gradle NOT FOUND. Auto-compile skipped.")
                    return msg

            if player: player.write_log(f"Using Gradle at: {gradle_bin}")

            # Explicit Environment Injection
            env = os.environ.copy()
            java_home = os.environ.get("JAVA_HOME", r"C:\Program Files\Java\jdk-17")
            android_home = os.environ.get("ANDROID_HOME", r"C:\AndroidSDK")
            gradle_bin_dir = os.path.join(gradle_bin_path, "bin")

            # Set critical environment variables
            if os.path.exists(java_home):
                env["JAVA_HOME"] = java_home
            
            if os.path.exists(android_home):
                env["ANDROID_HOME"] = android_home

            # Reconstruct PATH
            path_additions = [
                os.path.join(java_home, "bin"),
                os.path.join(android_home, "cmdline-tools", "latest", "bin"),
                os.path.join(android_home, "platform-tools"),
                gradle_bin_dir
            ]
            
            existing_path = env.get("PATH", "")
            env["PATH"] = ";".join(path_additions) + ";" + existing_path
            if player: player.write_log("Meticulously reconstructed PATH for compilation.")

            # 8. Run the build
            # We use 'assembleDebug' to generate the APK
            build_proc = subprocess.run(
                [gradle_bin, "assembleDebug"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                shell=True,
                env=env
            )
            
            if build_proc.returncode == 0:
                apk_path = project_dir / "app/build/outputs/apk/debug/app-debug.apk"
                desktop_apk = Path.home() / "Desktop" / f"{app_name}.apk"
                
                if apk_path.exists():
                    shutil.copy(apk_path, desktop_apk)
                    msg += f"🔥 BOOM! THE APK IS READY, SIR. I have compiled the code and saved '{app_name}.apk' directly to your Desktop."
                    if player: player.write_log("APK successfully compiled and moved to Desktop!")
                else:
                    msg += "Build succeeded, but I couldn't locate the final APK file in the standard output directory."
                    if player: player.write_log("Build succeeded, but APK file missing.")
            else:
                # Capture the specific error from Gradle
                error_summary = build_proc.stderr if build_proc.stderr else build_proc.stdout
                msg += f"Architecture complete, but compilation failed.\n\nERROR LOG:\n{error_summary[:1000]}"
                if player: 
                    player.write_log("Compilation failed. Check error logs below.")
                    print(f"[APKBuilder] Gradle Error:\n{error_summary}")

        except Exception as compile_err:
            msg += f"\n(Auto-compile attempt failed: {compile_err})"
            if player: player.write_log(f"Error during compilation attempt: {compile_err}")

        return msg

    except Exception as e:
        error_msg = f"APK generation failed: {e}"
        print(f"[APKBuilder] {error_msg}")
        return error_msg
ummary[:1000]}"
                if player: 
                    player.write_log("Compilation failed. Check error logs below.")
                    print(f"[APKBuilder] Gradle Error:\n{error_summary}")

        except Exception as compile_err:
            msg += f"\n(Auto-compile attempt failed: {compile_err})"
            if player: player.write_log(f"Error during compilation attempt: {compile_err}")

        return msg

    except Exception as e:
        error_msg = f"APK generation failed: {e}"
        print(f"[APKBuilder] {error_msg}")
        return error_msg
