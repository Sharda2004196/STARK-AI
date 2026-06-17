import cv2
from cvzone.HandTrackingModule import HandDetector
import pyautogui
import threading
import time
import numpy as np

# --- CONFIG ---
# ID 4: Thumb Tip
# ID 8: Index Tip
# ID 12: Middle Tip
# ID 0: Wrist

class GestureController(threading.Thread):
    def __init__(self, player=None):
        super().__init__()
        self.daemon = True
        self.player = player
        self.running = False
        
        # cvzone HandDetector handles mediapipe under the hood
        self.detector = HandDetector(staticMode=False, maxHands=1, modelComplexity=1, detectionCon=0.7, minTrackCon=0.7)
        
        # Screen dimensions
        self.screen_w, self.screen_h = pyautogui.size()
        
        # Smoothing variables - Reduced from 7 to 4 for much snappier movement
        self.smoothening = 4
        self.plocX, self.plocY = 0, 0
        self.clocX, self.clocY = 0, 0
        
        # Gesture states
        self.is_clicking = False
        self.last_scroll_time = 0
        self.last_fist_time = 0

    def run(self):
        self.running = True
        cap = cv2.VideoCapture(0)
        cap.set(3, 640)
        cap.set(4, 480)
        
        if self.player:
            self.player.write_log("Gesture Control: Camera initialized.")

        # Ensure fail-safe is enabled so we can throw cursor to corner to stop if needed
        pyautogui.FAILSAFE = True

        while self.running:
            success, img = cap.read()
            if not success:
                continue

            img = cv2.flip(img, 1)
            img_h, img_w, _ = img.shape
            
            # Find hands and landmarks using cvzone (draw=True gives visual feedback)
            hands, img = self.detector.findHands(img, draw=True, flipType=False)
            
            if hands:
                hand = hands[0]
                lmList = hand["lmList"] # List of 21 landmarks [x, y, z]
                
                # Check for "Fist" Gesture using fingersUp (cvzone built-in)
                # 0 means closed, 1 means open. [Thumb, Index, Middle, Ring, Pinky]
                fingers = self.detector.fingersUp(hand)
                
                # If all fingers are closed (fist)
                if fingers.count(0) == 5:
                    if time.time() - self.last_fist_time > 1.5:  # 1.5s cooldown
                        # Win+D minimizes all windows
                        pyautogui.hotkey('win', 'd')
                        if self.player: self.player.write_log("Gesture: Fist -> Minimized Windows")
                        self.last_fist_time = time.time()
                
                # Only process pointing/clicking if index finger is UP
                elif len(lmList) >= 13 and fingers[1] == 1:
                    x1, y1 = lmList[8][0], lmList[8][1]   # Index tip
                    x2, y2 = lmList[12][0], lmList[12][1] # Middle tip
                    x_thumb, y_thumb = lmList[4][0], lmList[4][1] # Thumb tip
                    
                    # 2. Mouse Movement (Index Finger)
                    frame_r = 100 # reduction
                    cv2.rectangle(img, (frame_r, frame_r), (img_w - frame_r, img_h - frame_r), (255, 0, 255), 2)
                    
                    # Map coordinates
                    mx = np.interp(x1, (frame_r, img_w - frame_r), (0, self.screen_w))
                    my = np.interp(y1, (frame_r, img_h - frame_r), (0, self.screen_h))
                    
                    # Smoothen
                    self.clocX = self.plocX + (mx - self.plocX) / self.smoothening
                    self.clocY = self.plocY + (my - self.plocY) / self.smoothening
                    
                    try:
                        pyautogui.moveTo(self.clocX, self.clocY)
                    except pyautogui.FailSafeException:
                        pass # Ignore corner fail-safe crashes during tracking
                        
                    self.plocX, self.plocY = self.clocX, self.clocY
                    
                    # 3. Left Click (Pinch: Index + Thumb)
                    dist_click, _, img = self.detector.findDistance((x1, y1), (x_thumb, y_thumb), img)
                    if dist_click < 40:
                        cv2.circle(img, (x1, y1), 15, (0, 255, 0), cv2.FILLED) # Visual feedback green circle
                        if not self.is_clicking:
                            pyautogui.click()
                            self.is_clicking = True
                            if self.player: self.player.write_log("Gesture: Left Click")
                    else:
                        self.is_clicking = False
                        
                    # 4. Right Click (Pinch: Middle + Thumb)
                    if fingers[2] == 1: # Only if middle finger is also up
                        dist_right, _, img = self.detector.findDistance((x2, y2), (x_thumb, y_thumb), img)
                        if dist_right < 40:
                            cv2.circle(img, (x2, y2), 15, (255, 0, 0), cv2.FILLED) # Visual feedback blue circle
                            pyautogui.rightClick()
                            time.sleep(0.3) # prevent multiple clicks
                            if self.player: self.player.write_log("Gesture: Right Click")
                            
                    # 5. Scroll (Index + Middle close together)
                    if fingers[1] == 1 and fingers[2] == 1:
                        dist_scroll, _, _ = self.detector.findDistance((x1, y1), (x2, y2), img=None)
                        if dist_scroll < 40:
                            if time.time() - self.last_scroll_time > 0.1:
                                if y1 < img_h // 3:
                                    pyautogui.scroll(120)
                                elif y1 > (2 * img_h) // 3:
                                    pyautogui.scroll(-120)
                                self.last_scroll_time = time.time()
            
            # Show the visual feedback window
            cv2.imshow("JARVIS Gesture Vision", img)
            
            # Stop if window is closed manually
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
                break
                
            # Tiny sleep to prevent 100% CPU lockup
            time.sleep(0.01)
            
        cap.release()
        cv2.destroyAllWindows()

    def stop(self):
        self.running = False

# Global instance manager
_GESTURE_CONTROLLER = None

def gesture_control(parameters: dict, player=None, **kwargs) -> str:
    global _GESTURE_CONTROLLER
    action = parameters.get("action", "start").lower()
    
    if action == "start":
        if _GESTURE_CONTROLLER and _GESTURE_CONTROLLER.is_alive():
            return "Gesture control is already running, sir."
        
        _GESTURE_CONTROLLER = GestureController(player=player)
        _GESTURE_CONTROLLER.start()
        return "Gesture control activated. Use index to point, pinch to click, and close fist to minimize windows."
    
    elif action == "stop":
        if _GESTURE_CONTROLLER:
            _GESTURE_CONTROLLER.stop()
            _GESTURE_CONTROLLER = None
            return "Gesture control has been deactivated, sir."
        return "Gesture control was not running."
    
    elif action == "status":
        status = "running" if (_GESTURE_CONTROLLER and _GESTURE_CONTROLLER.is_alive()) else "stopped"
        return f"Gesture control is currently {status}."

    return f"Unknown gesture action: {action}"
