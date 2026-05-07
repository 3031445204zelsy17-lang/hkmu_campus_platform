// Supabase setup
// Safe to expose in browser: use the Project URL and anon/publishable key only.
// Never paste the service_role key into frontend code.
const SUPABASE_URL = 'https://lyekkcdcaoolyzusuzfx.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_ZeSxBaYvt-N8qn2vZ4ugtA_CgCycxUC';

const muwallDb = window.supabase?.createClient
    ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
        auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true
        }
    })
    : null;

window.muwallDb = muwallDb;
window.muwallSupabase = muwallDb;
if (muwallDb) {
    console.log('Supabase client initialized');
} else {
    console.error('Supabase SDK failed to load. Check the CDN script in index.html.');
}

let currentLang = localStorage.getItem('muwall_lang') || 'zh-cn';

function getCurrentUser() {
    const saved = localStorage.getItem('muwallCurrentUser');
    return saved ? JSON.parse(saved) : null;
}

function setCurrentUser(user) {
    if (user) {
        localStorage.setItem('muwallCurrentUser', JSON.stringify(user));
    } else {
        localStorage.removeItem('muwallCurrentUser');
    }
}

let currentUser = getCurrentUser();

function buildCurrentUser(authUser, profile = null) {
    if (!authUser) return null;

    const meta = authUser.user_metadata || {};
    return {
        id: authUser.id,
        email: authUser.email || profile?.email || '',
        username: profile?.username || meta.username || authUser.email?.split('@')[0] || 'User',
        identity: profile?.identity || meta.identity || 'student',
        avatar: profile?.avatar || meta.avatar || 'icon/default.png',
        major: profile?.major || meta.major || '',
        bio: profile?.bio || meta.bio || ''
    };
}

async function getProfileByUserId(userId) {
    if (!userId) return null;

    const { data, error } = await muwallDb
        .from('profiles')
        .select('id, email, username, identity, avatar, major, bio')
        .eq('id', userId)
        .maybeSingle();

    if (error) {
        console.warn('Could not load profile from Supabase:', error.message);
        return null;
    }

    return data;
}

async function syncCurrentUserFromSession(session) {
    if (!session?.user) {
        currentUser = null;
        setCurrentUser(null);
        if (typeof updateProfileUI === 'function') updateProfileUI(null);
        return null;
    }

    const profile = await getProfileByUserId(session.user.id);
    currentUser = buildCurrentUser(session.user, profile);
    setCurrentUser(currentUser);
    if (typeof updateProfileUI === 'function') updateProfileUI(currentUser);

    return currentUser;
}

async function saveUserProfile(profileInput) {
    if (!currentUser?.id) throw new Error('You must log in first.');

    const profile = {
        id: currentUser.id,
        email: currentUser.email,
        username: profileInput.username || currentUser.username || 'User',
        identity: profileInput.identity || currentUser.identity || 'student',
        avatar: profileInput.avatar || currentUser.avatar || 'icon/default.png',
        major: profileInput.major || '',
        bio: profileInput.bio || '',
        updated_at: new Date().toISOString()
    };

    const { data, error } = await muwallDb
        .from('profiles')
        .upsert(profile, { onConflict: 'id' })
        .select('id, email, username, identity, avatar, major, bio')
        .single();

    if (error) throw error;

    const { error: metadataError } = await muwallDb.auth.updateUser({
        data: {
            username: data.username,
            identity: data.identity,
            avatar: data.avatar,
            major: data.major,
            bio: data.bio
        }
    });

    if (metadataError) {
        console.warn('Profile saved, but auth metadata was not updated:', metadataError.message);
    }

    currentUser = { ...currentUser, ...data };
    setCurrentUser(currentUser);
    if (typeof updateProfileUI === 'function') updateProfileUI(currentUser);

    return currentUser;
}

if (muwallDb) {
    muwallDb.auth.getSession().then(({ data: { session } }) => {
        syncCurrentUserFromSession(session);
    });

    muwallDb.auth.onAuthStateChange((event, session) => {
        if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED' || event === 'USER_UPDATED') {
            syncCurrentUserFromSession(session);
        } else if (event === 'SIGNED_OUT') {
            syncCurrentUserFromSession(null);
        }
    });
}

// Local fallback helpers kept for old localStorage data migration/debugging.
function getLocalUsers() {
    const saved = localStorage.getItem('muwallUsers');
    return saved ? JSON.parse(saved) : [];
}

function saveLocalUsers(users) {
    localStorage.setItem('muwallUsers', JSON.stringify(users));
}

function addLocalUser(user) {
    const users = getLocalUsers();
    users.push(user);
    saveLocalUsers(users);
}

function findLocalUser(username) {
    return getLocalUsers().find(u => u.username === username);
}

function updateLocalUser(updatedUser) {
    const users = getLocalUsers().map(u => u.username === updatedUser.username ? updatedUser : u);
    saveLocalUsers(users);
}

const translations = {
    'zh-cn': {},
    'zh': {},
    'en': {}
};

async function testSupabase() {
    if (!muwallDb) {
        console.warn('Supabase connection skipped because SDK is not available.');
        return;
    }

    const { error } = await muwallDb.from('posts').select('id').limit(1);
    if (error) {
        console.warn('Supabase connection failed:', error.message);
    } else {
        console.log('Supabase connection OK');
    }
}
testSupabase();

(function injectToastStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .muwall-toast {
            position: fixed;
            top: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(-120%);
            padding: 14px 28px;
            border-radius: 12px;
            color: #fff;
            font-size: 15px;
            font-weight: 600;
            z-index: 99999;
            opacity: 0;
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
            pointer-events: none;
            box-shadow: 0 8px 32px rgba(0,0,0,0.18);
            backdrop-filter: blur(12px);
            max-width: 90vw;
            text-align: center;
        }
        .muwall-toast.show {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
        .muwall-toast.success {
            background: linear-gradient(135deg, #34d399, #059669);
        }
        .muwall-toast.error {
            background: linear-gradient(135deg, #f87171, #dc2626);
        }
        .muwall-toast.info {
            background: linear-gradient(135deg, #60a5fa, #2563eb);
        }
    `;
    document.head.appendChild(style);
})();

function showToast(message, type = 'info', duration = 3000) {
    const existing = document.querySelector('.muwall-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `muwall-toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

window.addEventListener('DOMContentLoaded', () => {
    const pendingToast = sessionStorage.getItem('muwall_pending_toast');
    if (pendingToast) {
        sessionStorage.removeItem('muwall_pending_toast');
        const { message, type } = JSON.parse(pendingToast);
        setTimeout(() => showToast(message, type), 500);
    }
});
