# If the jury asks: plain answers

Read this once. Every answer is one or two sentences you can say in your own words.

**What does the bot do?**
It quotes a price to each car dealer, and if it wins the car it posts the job for a freelance driver at a fee it chooses. It tries to make money while keeping at least 90% of cars on time.

**Why does a market-making paper explain a delivery bot?**
A market maker quotes a price, earns the gap over its cost, and manages a limited resource. We quote a price, earn the gap over the driver cost, and the limited resource is drivers. The same rule fits: price = cost + markup + the price of whatever is scarce, and that price is zero until the scarce thing runs short.

**What was the biggest win?**
Putting two cars in one gig. A second car that starts where the first ends removes a trip for the driver, so pairs book at about three quarters of the single-car fee. About €1,600 a week.

**How do you know it isn't just tuned to your practice weeks?**
We kept 12 weeks that were never used for tuning and checked every important change on them. The margin held. The on-time share did not at first (one week at 90.4%), so we found why and fixed it.

**Why not win every car?**
Drivers are scarce. Winning cars with no driver to move them means late cars, refunds and a drop under the 90% line. The bot declines cars it can't deliver on time, by quoting very high.

**What happens if it crashes during the final?**
A launcher restarts it within seconds. It saves its state every four seconds and rebuilds from the server's record. We rehearsed this by killing it twice mid-week: it carried on and stayed ranked.

**What didn't work?**
Discounting to build dealer trust (about −€900 a week), direct offers to drivers (4 accepted of 666), fee steps by gig age (−€900 to −€1,700), and refitting on our own results (selection bias). Each is a switch we can turn back on.

**What don't you know?**
The competitor's real prices, the drivers' real costs and the exact shape of dealer acceptance. We estimate them from our own wins, losses and bookings.

**Who built this?** (answer honestly; the paper already discloses its AI help)
Aarin led the project and wrote the paper the pricing rule comes from. The code was built and tested with AI coding assistants, which ran the experiments and wrote the programs. Aarin chose the direction, decided what to keep, and approved every step.

## Numbers to remember
- Kit starter: −€72,613 a week, 45.5% on time. Ours: about €16,700 a week in practice, about €15–16k on unseen weeks, 94–97% on time.
- The gate: 90% on time. Worst practice week: 94.1%.
- Biggest wins: two cars per gig (+€1,640), counting drivers beyond 30 km (+€2,448), the late-risk brake (+€359 and a safer worst week), notes reader (about +€2,300).
