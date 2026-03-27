import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { authFetch } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

async function ensureAndroidChannel() {
  if (Platform.OS !== "android") {
    return;
  }

  await Notifications.setNotificationChannelAsync("default", {
    name: "default",
    importance: Notifications.AndroidImportance.MAX,
  });
}

export async function registerForPushNotifications(): Promise<string | null> {
  await ensureAndroidChannel();

  if (!Device.isDevice) {
    return null;
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== "granted") {
    return null;
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ||
    Constants.easConfig?.projectId;

  const tokenResponse = await Notifications.getExpoPushTokenAsync(
    projectId ? { projectId } : undefined,
  );

  return tokenResponse.data;
}

export async function registerPushTokenOnBackend(
  pushToken: string,
  role: "STUDENT" | "PROFESSOR",
  regNo?: string,
) {
  try {
    await authFetch("/api/notifications/register-device", {
      method: "POST",
      body: JSON.stringify({
        push_token: pushToken,
        platform: Platform.OS,
        role,
        reg_no: regNo || null,
      }),
    });
  } catch (error) {
    console.warn("Device push token registration failed", error);
  }
}
