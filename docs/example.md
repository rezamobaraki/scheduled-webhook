````md
# Understanding the Problem

## ⏰ What is a Job Scheduler

A **job scheduler** is a program that automatically schedules and executes jobs at specified times or intervals. It is used to automate repetitive tasks, run scheduled maintenance, or execute batch processes.

There are two key terms worth defining before we jump into solving the problem:

- **Task**: A task is the abstract concept of work to be done. For example, `"send an email"`. Tasks are reusable and can be executed multiple times by different jobs.
- **Job**: A job is an instance of a task. It is made up of the task to be executed, the schedule for when the task should be executed, and parameters needed to execute the task. For example, if the task is `"send an email"`, then a job could be `"send an email to john@example.com at 10:00 AM Friday"`.

The main responsibility of a job scheduler is to take a set of jobs and execute them according to the schedule.

---

# Functional Requirements

## Core Requirements

- Users should be able to schedule jobs to be executed immediately, at a future date, or on a recurring schedule (i.e. `"every day at 10:00 AM"`).
- Users should be able monitor the status of their jobs.

## Below the line (out of scope)

- Users should be able to cancel or reschedule jobs.

---

# Non-Functional Requirements

Now is a good time to ask about the scale of the system in your interview. If I were your interviewer, I would explain that the system should be able to execute **10k jobs per second**.

## Core Requirements

- The system should be highly available (**availability > consistency**).
- The system should execute jobs within **2s** of their scheduled time.
- The system should be scalable to support up to **10k jobs per second**.
- The system should ensure **at-least-once execution** of jobs.

## Below the line (out of scope)

- The system should enforce security policies.
- The system should have a CI/CD pipeline.

On the whiteboard, this might look like:

## Requirements

---

# The Set Up

## Planning the Approach

For this question, which is less of a user-facing product and more focused on data processing, we're going to follow the delivery framework outlined here, focusing on the **core entities**, then the **API**, and then the **data flow** before diving into the **high-level design** and ending with **deep dives**.

---

# Defining the Core Entities

We recommend that you start with a broad overview of the primary entities, even for questions more focused on infrastructure, like this one. It is not necessary to know every specific column or detail yet. We will focus on the intricacies, such as columns and fields, later when we have a clearer grasp of the system.

Just make sure that you let your interviewer know your plan so you're on the same page. I'll often explain that I'm going to start with just a simple list, but as we get to the high-level design, I'll document the data model more thoroughly.

To satisfy our key functional requirements, we'll need the following entities:

- **Task**: Represents a task to be executed.
- **Job**: Represents an instance of a task to be executed at a given time with a given set of parameters.
- **Schedule**: Represents a schedule for when a job should be executed, either a CRON expression or a specific DateTime.
- **User**: Represents a user who can schedule jobs and view the status of their jobs.

In the actual interview, this can be as simple as a short list like this. Just make sure you talk through the entities with your interviewer to ensure you are on the same page.

## Entities

---

# The API

Your goal is to simply go one-by-one through the core requirements and define the APIs that are necessary to satisfy them. Usually, these map 1:1 to the functional requirements, but there are times when multiple endpoints are needed to satisfy an individual functional requirement.

First, let's create a job:

```http
POST /jobs
````

```json
{
  "task_id": "send_email",
  "schedule": "0 10 * * *",
  "parameters": {
    "to": "john@example.com",
    "subject": "Daily Report"
  }
}
```

Next, let's query the status of our jobs:

```http
GET /jobs?user_id={user_id}&status={status}&start_time={start_time}&end_time={end_time} -> Job[]
```

---

# Data Flow

Before diving into the technical design, let's understand how data flows through our system. The data flow represents the journey from when a request enters our system to when it produces the final output.

Understanding this flow early in our design process serves multiple purposes:

1. It helps ensure we're aligned with our interviewer on the core functionality before getting into implementation details.
2. It provides a clear roadmap that will guide our high-level design decisions.
3. It allows us to identify potential bottlenecks or issues before we commit to specific architectural choices.

### Flow

1. A user schedules a job by providing the task to be executed, the schedule for when the task should be executed, and the parameters needed to execute the task.
2. The job is persisted in the system.
3. The job is picked up by a worker and executed at the scheduled time.
4. If the job fails, it is retried with exponential backoff.
5. Update the job status in the system.

Note that this is simple, we will improve upon as we go, but it's important to start simple and build up from there.

---

# High-Level Design

We start by building an MVP that works to satisfy the core functional requirements. This does not need to scale or be perfect. It's just a foundation for us to build upon later. We will walk through each functional requirement, making sure each is satisfied by the high-level design.

---

## 1) Users should be able to schedule jobs to be executed immediately, at a future date, or on a recurring schedule

When a user schedules a job, they'll provide:

* the task to be executed,
* the schedule for when the job should be executed,
* and the parameters needed to execute the task.

Let's walk through how this works:

The user makes a request to a `/jobs` endpoint with:

* **Task ID** (which task to run)
* **Schedule** (when to run it)
* **Parameters** (what inputs the task needs)

We store the job in our database with a status of `PENDING`. This ensures that:

* We have a persistent record of all jobs
* We can recover jobs if our system crashes
* We can track the job's status throughout its lifecycle

## Schedule Jobs

When it comes to choosing a database, the hard truth is that any modern database will work. Given no need for strong consistency and our data has few relationships, I'm going to opt for a flexible key value store like **DynamoDB** to make scaling later on easier. If you're interviewing at a company that prefers open-source solutions, you might go with **Cassandra** instead. But, like I said, **Postgres** or **MySQL** would work just as well, you'd just need to pay closer attention to scaling later on.

Let's start with a simple schema for our `Jobs` table to see why this approach needs refinement:

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "user_123",
  "task_id": "send_email",
  "scheduled_at": 1715548800,
  "parameters": {
    "to": "john@example.com",
    "subject": "Daily Report"
  },
  "status": "PENDING"
}
```

This works fine for one-time jobs, but it breaks down when we consider recurring schedules.

Consider a daily email report that needs to run at 10 AM every day. We could store the CRON expression (`0 10 * * *`) in our table, but then how do we efficiently find which jobs need to run in the next few minutes? We'd need to evaluate every single CRON expression in our database—clearly not scalable.

This brings us to a key insight: **we need to separate the definition of a job from its execution instances**.

Think of it like a calendar: you might have an event that repeats every Monday, but in your calendar app, you see individual instances of that event on each Monday. This is exactly what we need.

Let's split our data into two tables.

### Jobs table

Stores the job definitions:

```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "user_123",
  "task_id": "send_email",
  "schedule": {
    "type": "CRON | DATE",
    "expression": "0 10 * * *"
  },
  "parameters": {
    "to": "john@example.com",
    "subject": "Daily Report"
  }
}
```

### Executions table

Tracks each individual time a job should run:

```json
{
  "time_bucket": 1715547600,
  "execution_time": "1715548800-123e4567-e89b-12d3-a456-426614174000",
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "user_123",
  "status": "PENDING",
  "attempt": 0
}
```

By using a **time bucket** (Unix timestamp rounded down to the nearest hour) as our partition key, we can efficiently query for upcoming jobs. We only need to query the current hour's bucket and possibly the next hour's bucket.

The time bucket can be easily calculated:

```python
time_bucket = (execution_time // 3600) * 3600  # Round down to nearest hour
```

This gives us efficient reads, since we only need to query 1–2 partitions to find all upcoming jobs.

When a recurring job completes, we can easily schedule its next occurrence by calculating the next execution time and creating a new entry in the `Executions` table. The job definition stays the same, but we keep creating new execution instances.

Concentrating all writes for a given hour into a single partition could create a hot partition under heavy load. We'll address this with **write sharding** in the scaling deep dive.

This pattern of separating the definition of something from its instances is common in system design. You'll see it in:

* calendar systems (event definition vs. occurrences),
* notification systems (template vs. individual notifications),
* and many other places.

When a worker node is ready to execute jobs, it simply queries the `Executions` table for entries where:

* `execution_time` is within the next few minutes
* `status` is `"PENDING"`

The worker can then look up the full job details in the `Jobs` table and execute the task.

## Execution

This simple approach is a great start, but don't stop reading here. We expand on this significantly later in the deep dives in order to ensure the system is scalable, fault tolerant, and handles job failures gracefully.

---

## 2) Users should be able monitor the status of their jobs

First, the obvious bit: when a job is executed we need to update the status on the `Executions` table with any of:

* `COMPLETED`
* `FAILED`
* `IN_PROGRESS`
* `RETRYING`

## Monitoring

But how can we query for the status of all jobs for a given user?

With the current design, querying jobs by `user_id` would require an inefficient two-step process:

1. Query the `Jobs` table to find all `job_id`s for a user (an inefficient full table scan)
2. Query the `Executions` table to find the status of each job

To solve this, we'll add a **Global Secondary Index (GSI)** on the `Executions` table:

* **Partition Key**: `user_id`
* **Sort Key**: `execution_time + job_id`

This GSI allows us to efficiently:

* find all executions for a user,
* sort them by execution time,
* support pagination,
* and filter by status if needed.

The GSI adds some write overhead and cost, but it's a worthwhile trade-off to support efficient user queries without compromising our primary access pattern of finding jobs that need to run soon.

This is a common pattern in DynamoDB (and similar NoSQL databases) where you maintain multiple access patterns through GSIs rather than denormalizing the data.

Now, users simply need to query the GSI by `user_id` and get a list of executions sorted by `execution_time`.

---

# Potential Deep Dives

## 1) How can we ensure the system executes jobs within 2s of their scheduled time?

Our current design has some key limitations that prevent us from executing jobs at the precision we require.

The most obvious limitation is that we are querying the database every few minutes to find jobs that are due for execution. The frequency with which we decide to run our cron that queries for upcoming jobs is naturally the upper bound of how often we can be executing jobs. If we ran the cron every 2 minutes, then a job could be executed as much as 2 minutes early or late.

The next consideration would be to run the cron more frequently. However, to meet our precision requirement, this would mean running it every 2 seconds or less. This won't work for several reasons:

* With **10k jobs per second**, each query would need to fetch and process around **20k jobs**.
* Even with proper indexing, querying for 20k jobs could take several hundred milliseconds.
* After retrieving the jobs, we still need time to initialize them, distribute them to workers, and begin execution.
* Running such large queries every 2 seconds puts significant load on the database.

As you can see, this isn't the best idea. Instead, we can get more clever and introduce a **two-layered scheduler architecture** which marries durability with precision.

### Phase 1: Query the database

Just like in our current design, we query the `Executions` table for jobs that are due for execution in the next ~5 minutes.

### Phase 2: Message queue

We take the list of jobs returned by our query and push them to a message queue, ordered by `execution_time`. Workers then pull jobs from the queue in order and execute them.

## Low Latency

This two-layered approach provides significant advantages by decoupling the database querying from job execution. By running database queries just once every 5 minutes, we reduce database load while maintaining precision through the message queue.

Okay, we're making progress, but what about new jobs that are created and expected to run in less than 5 minutes?

Currently, we'd write this job to the database, but the cron that runs every 5 minutes would never see it in time.

We could try to put the job directly into the message queue, but this introduces a problem with log-based queues like Kafka. Kafka processes messages in order within a partition, so a new job would go to the end of the partition and wait behind all the jobs already queued — even if it's scheduled to run sooner.

Instead, we need a queue system that supports **delayed delivery**, so that jobs only become visible to workers at (or near) their scheduled execution time.

### Option 1: Redis Sorted Sets (ZSET)

**Approach**

Redis Sorted Sets offer a straightforward way to implement a priority queue, using the execution timestamp as the score for ordering.

**Challenges**

* Operational complexity in a distributed environment
* Need to implement your own retry logic
* Need to handle Redis replication carefully
* More custom code to run reliably in production

### Option 2: RabbitMQ

**Approach**

RabbitMQ provides a robust message queuing system with support for delayed message delivery using a **TTL + Dead Letter Exchange** pattern.

**Challenges**

* High availability requires **quorum queues**
* Clustering alone only replicates topology, not queue contents
* Delayed delivery via TTL + DLX adds complexity
* Horizontal scaling requires careful configuration and monitoring

### Option 3: Amazon SQS

**Approach**

Amazon SQS provides a fully managed queue service with native support for delayed message delivery.

For example, if we want to schedule a job to run in 10 seconds, we can send a message to SQS with a delay of 10 seconds. SQS will then deliver the message to our worker after the delay.

This eliminates the need for managing infrastructure while providing all the features we need out of the box.

It gives us:

* delayed message delivery,
* visibility timeouts,
* dead-letter queues,
* high availability across multiple availability zones,
* and automatic scaling.

For our use case, SQS would be the best choice due to its native support for delayed message delivery, automatic handling of worker failures, and excellent scaling characteristics for our load of 10k jobs per second.

> Keep in mind that `DelaySeconds` is a minimum delay, not a precision guarantee — but since workers are continuously polling the queue, any additional latency is typically negligible.

## Timely Execution

To recap, our new two-layered scheduler architecture looks like this:

1. A user creates a new job which is written to the database.
2. A cron job runs every 5 minutes to query the database for jobs that are due for execution in the next ~5 minutes.
3. The cron job sends these jobs to SQS with appropriate delay values.
4. Workers continuously poll SQS and process messages as they become visible.
5. If a new job is created with a scheduled time < 5 minutes from the current time, it's sent directly to SQS with the appropriate delay.

Keep in mind that many interviewers or companies will prefer that you avoid managed services like SQS. If this is the case, you can implement your own priority queue using Redis or a similar data store.

---

## 2) How can we ensure the system is scalable to support up to 10k jobs per second?

In any interview, when you get to talking about scale, my suggestion is to work left to right looking for bottlenecks and addressing them one by one.

### Job Creation

If job creation was evenly distributed with job execution, this would mean we have **10k jobs being created per second**.

To handle high job creation rates, we could introduce a message queue like Kafka or RabbitMQ between our API and Job Creation service. This queue acts as a buffer during traffic spikes.

That said, adding a message queue here is likely overcomplicating the design. The database should be able to handle the write throughput directly, and we can scale the service itself horizontally.

### Scalability

### Jobs DB

As discussed earlier, we chose DynamoDB or Cassandra for our `Jobs` and `Executions` tables.

This was a good choice for scale since DynamoDB supports up to 1,000 write capacity units per partition, and with proper key design, our data naturally spreads across many partitions.

#### Partition strategy

* **Jobs table**: Partitioned by `job_id`, which distributes writes evenly
* **Executions table**: Partitioned by `time_bucket`

Since all writes for the current hour land on the same partition, this could become a hot partition under heavy load.

To address this, we can add **write sharding** by appending a random suffix to the partition key:

```text
time_bucket#shard_3
```

Workers would then query all shards for a given time bucket in parallel.

With proper provisioning and sharding, these tables should handle our load of 10k operations per second.

Notably, once a job has been executed, we need to keep it around for users to query. But once a reasonable amount of time has passed (say **1 year**), we can move it off to a cheaper storage solution like **S3**.

### Message Queue Capacity

Let's do some quick math:

* **10k jobs/second**
* **300 seconds** in a 5-minute window
* Total = **3 million jobs** per 5-minute window

If each message is around **200 bytes**, that's only about **600MB** of data per 5-minute window.

SQS automatically handles scaling and message distribution across consumers, which is one of its biggest advantages.

With Standard queues, throughput is virtually unlimited, so our **10,000 messages per second** requirement is well within its capabilities.

We might still want multiple queues, but only for **functional separation**, not for scaling purposes.

## Scale

Even if you went with a Redis priority queue, 3 million jobs would easily fit in memory, so there's nothing to worry about there. You would just end up being more concerned with fault tolerance in case Redis goes down.

### Workers

For the worker layer, we need to carefully consider our compute options. The two main choices are:

* **Containers** (ECS or Kubernetes)
* **Lambda functions**

#### Containers

* More cost-effective for steady workloads
* Better suited for long-running jobs
* More operational overhead
* Less elastic than serverless

#### Lambda functions

* Minimal operational overhead
* Great for short-lived jobs under 15 minutes
* Auto-scale instantly
* Cold starts could impact the 2-second precision requirement
* More expensive for steady, high-volume workloads

Given our requirements — **10k jobs per second**, **2-second precision**, and a **steady predictable workload** — I’d use **containers with ECS and auto-scaling groups**.

Containers give us the best balance of cost efficiency and operational simplicity while meeting our performance needs.

We can optimize further by:

* using spot instances,
* auto-scaling based on queue depth,
* pre-warming the container pool,
* and setting scaling policies for unexpected spikes.

## Workers

---

## 3) How can we ensure at-least-once execution of jobs?

Our main concern is how we process failures. If a worker fails to process a job for any reason, we want to ensure that the job is retried a reasonable number of times before giving up (let's say **3 retries per job**).

Importantly, jobs can fail for one of two reasons:

* **Visible failure**: The job fails visibly, likely because of a bug in the task code or incorrect input parameters.
* **Invisible failure**: The job fails invisibly, likely because the worker itself went down.

### Visible failures

For visible failures, we wrap the task code in a `try/catch` block so that we can:

* log the error,
* mark the job as failed,
* and retry the job with exponential backoff.

Upon failure, we update the `Executions` table to set the job status to `RETRYING` with the number of attempts made so far.

We can then put the job back into the message queue (SQS) with an increasing delay for each retry attempt.

Example backoff:

* First retry: 5 seconds
* Second retry: 25 seconds
* Third retry: 125 seconds

If a job is retried 3 times and still fails, we mark it as `FAILED` in the `Executions` table.

SQS gives us the building blocks we need here:

* visibility timeouts,
* `ApproximateReceiveCount`,
* dead-letter queues.

We just need to implement the backoff timing logic in the worker code.

### Invisible failures

When a worker crashes or becomes unresponsive, we need a reliable way to detect this and retry the job.

### Approach 1: Health checks

**Approach**

Each worker exposes a `GET /health` endpoint. A central monitoring service continuously polls these endpoints.

**Challenges**

* Doesn't scale well with thousands of workers
* Network issues can trigger false positives
* Requires extra infrastructure
* Complex coordination is needed
* Monitoring service itself can fail

### Approach 2: Job leasing

**Approach**

Workers acquire a lease on a job by updating the database with:

* worker ID
* lease expiration timestamp

They must periodically renew this lease while processing.

If they stop renewing, another worker can acquire the lease and retry the job.

**Challenges**

* Frequent lease renewals create high database write volume
* Clock synchronization matters
* Network partitions can cause duplicate execution

### Approach 3: SQS visibility timeout

**Approach**

Amazon SQS provides a built-in mechanism for handling worker failures through **visibility timeouts**.

When a worker receives a message:

* SQS makes it invisible to other workers for a configurable period
* The worker processes the job
* The worker deletes the message on success
* If the worker crashes, the message becomes visible again after the timeout

To optimize for quick failure recovery while still supporting long-running jobs:

* set a short visibility timeout (e.g. 30 seconds),
* have workers periodically heartbeat by calling `ChangeMessageVisibility`

This way, if the worker crashes, another worker can retry the job quickly.

## Benefits

* No extra infrastructure needed
* Handles worker failures automatically
* Supports long-running jobs
* Fast failure detection
* Dead-letter queues handle max retry limits

## Retries

Lastly, one consequence of at-least-once execution is that we need to ensure our task code is **idempotent**.

In other words, running the task multiple times should have the same outcome as running it just once.

### Option 1: Do nothing

**Approach**

Execute the job every time it's received.

**Challenges**

This can lead to serious data consistency issues:

* duplicate emails,
* duplicate money transfers,
* counters incremented too many times.

Clearly not acceptable.

### Option 2: Deduplication table

**Approach**

Before executing a job, check a deduplication table to see if this specific job execution has already been processed.

Use a unique identifier such as:

* `job_id + execution_timestamp`

If a matching record exists, skip execution.

**Challenges**

* Adds database reads/writes to every job execution
* Requires cleanup over time
* Has a small race condition window

### Option 3: Naturally idempotent jobs

**Approach**

Design jobs to be naturally idempotent using:

* idempotency keys,
* conditional writes,
* downstream deduplication.

Examples:

* Instead of `"increment counter"`, use `"set counter to X"`
* Instead of `"send welcome email"`, first check whether the welcome email flag is already set

Each job execution includes a unique identifier that downstream services can use to deduplicate requests.

This is the most robust approach, essentially offloading idempotency concerns to the task's implementation.
