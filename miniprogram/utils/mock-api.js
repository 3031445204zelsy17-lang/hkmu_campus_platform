const DAY = 24 * 60 * 60 * 1000;

function daysAgo(days) {
  return new Date(Date.now() - days * DAY).toISOString();
}

const mockUser = {
  id: 1001,
  username: "preview_student",
  nickname: "HKMU Preview",
  email: "preview@hkmu.example",
  student_id: "S1234567",
  identity: "student",
  bio: "UI preview account for campus product review.",
  avatar_url: "",
  oauth_provider: "preview",
  created_at: daysAgo(28),
};

let posts = [
  {
    id: 1,
    title: "Best quiet study spots this week",
    content: "The library third floor is calmer after 6pm. The learning commons is good for group work before lunch.",
    category: "Campus",
    created_at: daysAgo(0.2),
    author_id: 21,
    author_nickname: "Mandy Chan",
    author_avatar: "",
    comments_count: 8,
    likes_count: 42,
    is_liked: false,
  },
  {
    id: 2,
    title: "Course registration reminder",
    content: "Remember to check prerequisites before adding electives. Some courses require department approval.",
    category: "Academic",
    created_at: daysAgo(1),
    author_id: 22,
    author_nickname: "Academic Office",
    author_avatar: "",
    comments_count: 3,
    likes_count: 31,
    is_liked: true,
  },
  {
    id: 3,
    title: "Basketball court meetup",
    content: "Casual game near Jockey Club campus at 5:30pm. Beginners welcome.",
    category: "Activity",
    created_at: daysAgo(2),
    author_id: 23,
    author_nickname: "Leo Wong",
    author_avatar: "",
    comments_count: 12,
    likes_count: 19,
    is_liked: false,
  },
  {
    id: 4,
    title: "Looking for project teammates",
    content: "Building a campus events prototype. Need one designer and one backend teammate.",
    category: "Help",
    created_at: daysAgo(3),
    author_id: 24,
    author_nickname: "Ivy Lee",
    author_avatar: "",
    comments_count: 5,
    likes_count: 16,
    is_liked: false,
  },
];

const newsItems = [
  {
    id: 1,
    title: "HKMU launches student innovation showcase",
    summary: "Student teams present campus service ideas, research prototypes, and community projects.",
    category: "Campus",
    source_url: "https://www.hkmu.edu.hk/",
    published_at: daysAgo(0.5),
  },
  {
    id: 2,
    title: "Library extends opening hours during assessment period",
    summary: "Selected study areas will remain open later to support revision and group study.",
    category: "Student Support",
    source_url: "https://www.hkmu.edu.hk/",
    published_at: daysAgo(1.4),
  },
  {
    id: 3,
    title: "Career talk: preparing your first product portfolio",
    summary: "Alumni speakers share practical tips on internships, interviews, and portfolio storytelling.",
    category: "Career",
    source_url: "",
    published_at: daysAgo(2.5),
  },
  {
    id: 4,
    title: "Campus wellness week activities announced",
    summary: "Workshops, consultation booths, and peer support sessions will run across the week.",
    category: "Wellness",
    source_url: "",
    published_at: daysAgo(5),
  },
];

const lostFoundItems = [
  {
    id: 1,
    item_type: "lost",
    status: "active",
    title: "Black umbrella near Block C",
    description: "Foldable umbrella with a small silver label on the handle.",
    category: "Daily Items",
    location: "Block C entrance",
    author_nickname: "Alex",
    created_at: daysAgo(0.4),
  },
  {
    id: 2,
    item_type: "found",
    status: "active",
    title: "Student card found",
    description: "Found after the afternoon lecture. Please contact with your name and student ID.",
    category: "Card",
    location: "Lecture Theatre A",
    author_nickname: "Security Desk",
    created_at: daysAgo(1.1),
  },
  {
    id: 3,
    item_type: "lost",
    status: "resolved",
    title: "Blue water bottle",
    description: "Resolved item kept here to show the completed state in the UI.",
    category: "Bottle",
    location: "Library",
    author_nickname: "Tina",
    created_at: daysAgo(4),
  },
  {
    id: 4,
    item_type: "found",
    status: "active",
    title: "Wireless earbuds case",
    description: "White charging case found on a cafeteria table.",
    category: "Electronics",
    location: "Cafeteria",
    author_nickname: "Campus Helper",
    created_at: daysAgo(2.2),
  },
];

function parseRequestPath(path) {
  const parts = String(path || "").split("?");
  const pathname = parts[0] || "/";
  const query = {};

  if (parts[1]) {
    parts[1].split("&").forEach((pair) => {
      const entry = pair.split("=");
      if (entry[0]) {
        query[decodeURIComponent(entry[0])] = decodeURIComponent(entry[1] || "");
      }
    });
  }

  return { pathname, query };
}

function paginate(items, query) {
  const page = Math.max(Number(query.page || 1), 1);
  const pageSize = Math.max(Number(query.page_size || 12), 1);
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);

  return {
    has_next: start + pageSize < items.length,
    items: slice,
    page,
    page_size: pageSize,
    total: items.length,
  };
}

function matchesSearch(item, keyword) {
  const text = String(keyword || "").trim().toLowerCase();
  if (!text) {
    return true;
  }

  return [item.title, item.content, item.summary, item.category, item.description].some((value) =>
    String(value || "").toLowerCase().includes(text),
  );
}

function response(statusCode, data) {
  return Promise.resolve({
    data,
    statusCode,
  });
}

function tokens() {
  return {
    access_token: "preview-access-token",
    refresh_token: "preview-refresh-token",
    token_type: "bearer",
  };
}

function handlePosts(method, pathname, query, data) {
  if (method === "GET" && pathname === "/posts") {
    let items = posts.filter((item) => matchesSearch(item, query.search));

    if (query.sort === "hot") {
      items = items.slice().sort((a, b) => b.likes_count - a.likes_count);
    }

    return response(200, paginate(items, query));
  }

  if (method === "POST" && pathname === "/posts") {
    const nextPost = {
      id: Date.now(),
      title: data && data.title ? data.title : "Preview post",
      content: data && data.content ? data.content : "Preview content",
      category: data && data.category ? data.category : "Campus",
      created_at: new Date().toISOString(),
      author_id: mockUser.id,
      author_nickname: mockUser.nickname,
      author_avatar: "",
      comments_count: 0,
      likes_count: 0,
      is_liked: false,
    };

    posts = [nextPost].concat(posts);
    return response(201, nextPost);
  }

  const likeMatch = pathname.match(/^\/posts\/(\d+)\/like$/);
  if (method === "POST" && likeMatch) {
    const id = Number(likeMatch[1]);
    const post = posts.find((item) => item.id === id);
    if (!post) {
      return response(404, { detail: "Preview post not found" });
    }

    post.is_liked = !post.is_liked;
    post.likes_count += post.is_liked ? 1 : -1;
    return response(200, post);
  }

  return null;
}

function handleLostFound(method, pathname, query) {
  if (method !== "GET" || pathname !== "/lostfound") {
    return null;
  }

  let items = lostFoundItems.filter((item) => {
    const typeMatches = !query.item_type || item.item_type === query.item_type;
    const statusMatches = !query.status || item.status === query.status;
    return typeMatches && statusMatches;
  });

  items = items.filter((item) => matchesSearch(item, query.search));
  return response(200, paginate(items, query));
}

function handleNews(method, pathname, query) {
  if (method !== "GET" || pathname !== "/news") {
    return null;
  }

  return response(200, paginate(newsItems, query));
}

function mockRawRequest({ method = "GET", path, data = null }) {
  const normalizedMethod = String(method || "GET").toUpperCase();
  const { pathname, query } = parseRequestPath(path);

  if (
    normalizedMethod === "POST" &&
    ["/auth/login", "/auth/email/login", "/auth/wechat/miniprogram", "/auth/refresh"].includes(pathname)
  ) {
    return response(200, tokens());
  }

  if (normalizedMethod === "GET" && pathname === "/users/me") {
    return response(200, mockUser);
  }

  return (
    handlePosts(normalizedMethod, pathname, query, data) ||
    handleNews(normalizedMethod, pathname, query) ||
    handleLostFound(normalizedMethod, pathname, query) ||
    response(404, { detail: `Preview endpoint not found: ${pathname}` })
  );
}

module.exports = {
  mockRawRequest,
};
