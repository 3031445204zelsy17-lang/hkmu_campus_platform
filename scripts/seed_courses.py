"""Seed courses table with DSAI programme data and create test account."""
import asyncio
import aiosqlite
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from passlib.context import CryptContext

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

COURSES = [
    {"id":"COMP1080SEF","code":"COMP 1080SEF","name":"Introduction to Computer Programming","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Fundamental programming concepts using Python."},
    {"id":"IT1020SEF","code":"IT 1020SEF","name":"Computing Fundamentals","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Introduction to computer systems, hardware, software, and basic IT concepts."},
    {"id":"MATH1410SEF","code":"MATH 1410SEF","name":"Algebra and Calculus","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Mathematical foundations including linear algebra, differential and integral calculus."},
    {"id":"ENGL1101AEF","code":"ENGL 1101AEF","name":"University English: Reading and Writing","credits":3,"category":"english","year":1,"semester":"autumn","prerequisites":[],"description":"Academic English reading and writing skills for university-level coursework."},
    {"id":"GEN001","code":"GEN 001","name":"General Education Course 1","credits":3,"category":"general-ed","year":1,"semester":"autumn","prerequisites":[],"description":"First general education course covering broad interdisciplinary topics."},
    {"id":"UNI1002ABW","code":"UNI 1002ABW","name":"University Core Values","credits":2,"category":"university-core","year":1,"semester":"autumn","prerequisites":[],"description":"Introduction to university core values and academic integrity."},
    {"id":"UNI1012ABW","code":"UNI 1012ABW","name":"Social Responsibilities","credits":1,"category":"university-core","year":1,"semester":"autumn","prerequisites":[],"description":"Understanding social responsibilities and civic engagement."},
    {"id":"COMP2090SEF","code":"COMP 2090SEF","name":"Data Structures, Algorithms & Problem Solving","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":["COMP1080SEF"],"description":"Advanced data structures and algorithms for efficient problem solving."},
    {"id":"IT1030SEF","code":"IT 1030SEF","name":"Introduction to Internet Application Development","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Web development fundamentals including HTML, CSS, and JavaScript."},
    {"id":"STAT1510SEF","code":"STAT 1510SEF","name":"Probability & Distributions","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Probability theory and statistical distributions."},
    {"id":"STAT2610SEF","code":"STAT 2610SEF","name":"Data Analytics with Applications","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Introduction to data analytics methods and tools."},
    {"id":"ENGL1202EEF","code":"ENGL 1202EEF","name":"University English: Listening and Speaking","credits":3,"category":"english","year":1,"semester":"spring","prerequisites":[],"description":"Academic English listening and speaking skills."},
    {"id":"GEN002","code":"GEN 002","name":"General Education Course 2","credits":3,"category":"general-ed","year":1,"semester":"spring","prerequisites":[],"description":"Second general education course."},
    {"id":"COMP2020SEF","code":"COMP 2020SEF","name":"Java Programming Fundamentals","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Object-oriented programming with Java."},
    {"id":"COMP2640SEF","code":"COMP 2640SEF","name":"Discrete Mathematics","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Discrete mathematical structures for computer science."},
    {"id":"MATH2150SEF","code":"MATH 2150SEF","name":"Linear Algebra","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Advanced linear algebra concepts."},
    {"id":"STAT2510SEF","code":"STAT 2510SEF","name":"Statistical Data Analysis","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Statistical methods for data analysis."},
    {"id":"COMP2030SEF","code":"COMP 2030SEF","name":"Intermediate Java Programming & UI Design","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Advanced Java programming and user interface design."},
    {"id":"IT2900SEF","code":"IT 2900SEF","name":"Human Computer Interaction & UX Design","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Principles of human-computer interaction and user experience design."},
    {"id":"STAT2520SEF","code":"STAT 2520SEF","name":"Applied Statistical Methods","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Applied statistical methods for real-world problems."},
    {"id":"STAT2630SEF","code":"STAT 2630SEF","name":"Big Data Analytics with Applications","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Big data technologies and analytics applications."},
    {"id":"UNI2002BEW","code":"UNI 2002BEW","name":"Effective Communication and Teamwork","credits":3,"category":"university-core","year":2,"semester":"spring","prerequisites":[],"description":"Communication and teamwork skills for professional environments."},
    {"id":"COMP3200SEF","code":"COMP 3200SEF","name":"Database Management","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Database design, SQL, and database management systems."},
    {"id":"COMP3500SEF","code":"COMP 3500SEF","name":"Software Engineering","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Software engineering principles and practices."},
    {"id":"STAT3660SEF","code":"STAT 3660SEF","name":"SAS Programming","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Statistical analysis using SAS software."},
    {"id":"COMP3130SEF","code":"COMP 3130SEF","name":"Mobile Application Programming","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Mobile app development for iOS and Android platforms."},
    {"id":"ELEC3050SEF","code":"ELEC 3050SEF","name":"Computer Networking","credits":3,"category":"elective","year":3,"semester":"autumn","prerequisites":[],"description":"Computer network fundamentals and protocols."},
    {"id":"COMP3510SEF","code":"COMP 3510SEF","name":"Software Project Management","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":["COMP3500SEF"],"description":"Project management methodologies for software development."},
    {"id":"COMP3920SEF","code":"COMP 3920SEF","name":"Machine Learning","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Machine learning algorithms and applications."},
    {"id":"STAT3110SEF","code":"STAT 3110SEF","name":"Time Series Analysis & Forecasting","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Time series analysis and forecasting methods."},
    {"id":"COMP4820SEF","code":"COMP 4820SEF","name":"Data Mining And Analytics","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Data mining techniques and analytics."},
    {"id":"COMP4630SEF","code":"COMP 4630SEF","name":"Distributed Systems & Parallel Computing","credits":3,"category":"elective","year":3,"semester":"spring","prerequisites":[],"description":"Distributed systems and parallel computing concepts."},
    {"id":"MATH4950SEF","code":"MATH 4950SEF","name":"Professional Placement","credits":3,"category":"elective","year":3,"semester":"summer","prerequisites":[],"description":"Professional work placement in data science industry."},
    {"id":"COMP3810SEF","code":"COMP 3810SEF","name":"Server-side Technologies and Cloud Computing","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Server-side development and cloud computing platforms."},
    {"id":"COMP4330SEF","code":"COMP 4330SEF","name":"Advanced Programming & AI Algorithms","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Advanced AI algorithms and programming techniques."},
    {"id":"COMP4610SEF","code":"COMP 4610SEF","name":"Data Science Project","credits":6,"category":"project","year":4,"semester":"autumn","prerequisites":[],"description":"Capstone project in data science."},
    {"id":"COMP4930SEF","code":"COMP 4930SEF","name":"Deep Learning","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Deep learning and neural networks."},
    {"id":"COMP4210SEF","code":"COMP 4210SEF","name":"Advanced Database & Data Warehousing","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":["COMP3200SEF"],"description":"Advanced database systems and data warehousing."},
    {"id":"ELEC4310SEF","code":"ELEC 4310SEF","name":"Blockchain Technologies","credits":3,"category":"elective","year":4,"semester":"autumn","prerequisites":[],"description":"Blockchain technology and applications."},
    {"id":"UNI3002BEW","code":"UNI 3002BEW","name":"Entrepreneurial Mindset and Leadership for Sustainability","credits":3,"category":"university-core","year":4,"semester":"autumn","prerequisites":[],"description":"Entrepreneurship and leadership skills."},
    {"id":"ELEC3250SEF","code":"ELEC 3250SEF","name":"Computer & Network Security","credits":3,"category":"elective","year":4,"semester":"spring","prerequisites":["ELEC3050SEF"],"description":"Computer and network security principles."},
    {"id":"COMP4600SEF","code":"COMP 4600SEF","name":"Advanced Topics in Data Mining","credits":3,"category":"core","year":4,"semester":"spring","prerequisites":[],"description":"Advanced topics in data mining and knowledge discovery."},
    {"id":"ELEC4710SEF","code":"ELEC 4710SEF","name":"Digital Forensics","credits":3,"category":"elective","year":4,"semester":"spring","prerequisites":[],"description":"Digital forensics investigation techniques."},
]


async def seed():
    db_path = os.getenv("DATABASE_URL", "campus.db")
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    # Insert courses
    inserted = 0
    for c in COURSES:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO courses (id, code, name, credits, category, year, semester, prerequisites, description) VALUES (?,?,?,?,?,?,?,?,?)",
                (c["id"], c["code"], c["name"], c["credits"], c["category"], c["year"], c["semester"], str(c["prerequisites"]), c["description"]),
            )
            inserted += 1
        except Exception as e:
            print(f"  skip {c['id']}: {e}")

    # Create test user
    test_pw = pwd_ctx.hash("test123456")
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, nickname, student_id, identity) VALUES (?,?,?,?,?)",
            ("testuser", test_pw, "Test User", "12345678", "student"),
        )
    except Exception as e:
        print(f"  skip test user: {e}")

    await db.commit()

    # Verify
    count = (await (await db.execute("SELECT COUNT(*) FROM courses")).fetchone())[0]
    user_count = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    print(f"Seeded {inserted} courses ({count} in DB), {user_count} users")

    await db.close()


if __name__ == "__main__":
    asyncio.run(seed())
